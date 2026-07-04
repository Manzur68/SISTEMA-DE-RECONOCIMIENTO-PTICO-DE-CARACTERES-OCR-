import json
import logging
import os
import re
import signal
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

import cv2
import numpy as np
import pika
import pytesseract
from pytesseract import Output

from rabbitmq_config import (
    connect_with_retry, declare_queues, publish_message,
    start_consumer, QUEUE_OCR, QUEUE_CALIFICACION,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ms_ocr")

TESSERACT_CMD  = os.getenv("TESSERACT_CMD",  "tesseract")
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "spa+eng")

TESSERACT_CFG  = "--oem 3 --psm 6"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

CONF_ALTERNATIVA = 0.90

CONF_TEXTO_LIBRE = 0.30

PAT_ENUM = re.compile(r'^\s*(\d{1,2})\s*[.\-]\s+\S')

PREFIJOS = {
    'A': re.compile(r'^A\s*[\)\.]', re.IGNORECASE),
    'B': re.compile(r'^B\s*[\)\.]', re.IGNORECASE),
    'C': re.compile(r'^C\s*[\)\.]', re.IGNORECASE),
    'D': re.compile(r'^D\s*[\)\.]', re.IGNORECASE),
}

@dataclass
class ResultadoOCR:
    numero_pregunta : int
    texto_extraido  : str
    confianza       : float
    es_alternativa  : bool

def construir_lineas(datos: Dict) -> List[List[Dict]]:
    mapa = defaultdict(list)
    for i, word in enumerate(datos['text']):
        if str(word).strip() and datos['conf'][i] > 0:
            key = (datos['block_num'][i], datos['par_num'][i], datos['line_num'][i])
            mapa[key].append({
                'txt' : word.strip(),
                'x'   : datos['left'][i],
                'y'   : datos['top'][i],
                'conf': datos['conf'][i],
            })
    return sorted(mapa.values(), key=lambda ws: ws[0]['y'])

def texto_linea(ws: List[Dict]) -> str:
    return ' '.join(w['txt'] for w in sorted(ws, key=lambda w: w['x']))

def primera_palabra(txt: str) -> str:
    return txt.strip().split()[0] if txt.strip() else ""

def conf_linea(ws: List[Dict]) -> float:
    confs = [w['conf'] for w in ws if w['conf'] > 0]
    return round(sum(confs) / len(confs) / 100.0, 3) if confs else 0.0

def extraer_alternativas_inline(
    lineas: List[List[Dict]],
    ancho_imagen: int,
    num_preguntas_alt: int = 8,
) -> Dict[int, ResultadoOCR]:
    COL_SPLIT = ancho_imagen * 0.45

    def split(ws):
        izq = texto_linea([w for w in ws if w['x'] < COL_SPLIT])
        der = texto_linea([w for w in ws if w['x'] >= COL_SPLIT])
        return izq, der

    resultados: Dict[int, ResultadoOCR] = {}

    i = 0
    while i < len(lineas):
        txt = texto_linea(lineas[i])
        m   = PAT_ENUM.match(txt)

        if m:
            num = int(m.group(1))
            if 1 <= num <= num_preguntas_alt:
                fila1 = lineas[i + 1] if i + 1 < len(lineas) else []
                fila2 = lineas[i + 2] if i + 2 < len(lineas) else []

                if not fila1 or not fila2:
                    i += 1
                    continue

                f1_izq, f1_der = split(fila1)
                f2_izq, f2_der = split(fila2)

                celdas = {'A': f1_izq, 'B': f1_der, 'C': f2_izq, 'D': f2_der}

                marcada: Optional[str] = None
                for letra, contenido in celdas.items():
                    if contenido:
                        p1 = primera_palabra(contenido)
                        if p1 and not PREFIJOS[letra].match(p1):
                            marcada = letra
                            break

                if marcada:
                    logger.info(
                        f"  P{num}: marcada={marcada} "
                        f"(prefijo corrupto='{primera_palabra(celdas[marcada])}')"
                    )
                    resultados[num] = ResultadoOCR(
                        numero_pregunta = num,
                        texto_extraido  = marcada,
                        confianza       = CONF_ALTERNATIVA,
                        es_alternativa  = True,
                    )
                else:
                    logger.warning(f"  P{num}: no se detectó alternativa marcada")
                    resultados[num] = ResultadoOCR(
                        numero_pregunta = num,
                        texto_extraido  = "",
                        confianza       = 0.0,
                        es_alternativa  = True,
                    )

                i += 3
                continue
        i += 1

    return resultados

def extraer_texto_libre(
    lineas: List[List[Dict]],
    num_inicio: int = 9,
) -> Dict[int, ResultadoOCR]:
    resultados: Dict[int, ResultadoOCR] = {}

    for idx, ws in enumerate(lineas):
        txt = texto_linea(ws)
        m   = PAT_ENUM.match(txt)
        if not m:
            continue
        num = int(m.group(1))
        if num < num_inicio:
            continue

        partes = []
        for j in range(idx + 1, min(idx + 8, len(lineas))):
            sig = texto_linea(lineas[j])
            if PAT_ENUM.match(sig):
                break
            if re.match(r'^(SECCI[ÓO]N|Biolog)', sig, re.IGNORECASE):
                break
            if sig.strip():
                partes.append(sig.strip())

        if partes:
            texto_resp = ' '.join(partes)
            resultados[num] = ResultadoOCR(
                numero_pregunta = num,
                texto_extraido  = texto_resp,
                confianza       = CONF_TEXTO_LIBRE,
                es_alternativa  = False,
            )
            logger.info(
                f"  P{num} [texto libre]: '{texto_resp[:50]}' "
                f"→ pendiente_revision"
            )

    return resultados

def procesar_imagen_ocr(imagen_path: str) -> List[ResultadoOCR]:
    logger.info(f"OCR: {imagen_path}")

    img = cv2.imread(imagen_path)
    if img is None:
        raise FileNotFoundError(f"No se pudo cargar: {imagen_path}")

    ancho = img.shape[1]

    datos = pytesseract.image_to_data(
        img,
        lang=TESSERACT_LANG,
        config=TESSERACT_CFG,
        output_type=Output.DICT,
    )

    confs_ok = [c for c in datos['conf'] if c > 0]
    conf_global = round(sum(confs_ok) / len(confs_ok) / 100, 3) if confs_ok else 0.0
    logger.info(f"  Confianza global: {conf_global:.2f}")

    lineas = construir_lineas(datos)
    logger.info(f"  Líneas detectadas: {len(lineas)}")

    for ws in lineas[:60]:
        logger.debug(f"    y={ws[0]['y']:4d} | {texto_linea(ws)}")

    res_alt = extraer_alternativas_inline(lineas, ancho, num_preguntas_alt=8)
    logger.info(f"  Alternativas detectadas: {len(res_alt)}/8")

    res_txt = extraer_texto_libre(lineas, num_inicio=9)
    logger.info(f"  Preguntas texto libre  : {len(res_txt)}")

    todos = {**res_alt, **res_txt}
    return sorted(todos.values(), key=lambda r: r.numero_pregunta)

def combinar_paginas(paginas: List[List[ResultadoOCR]]) -> List[ResultadoOCR]:
    combinado: Dict[int, ResultadoOCR] = {}
    for pagina in paginas:
        for r in pagina:
            n = r.numero_pregunta
            if n not in combinado or r.confianza > combinado[n].confianza:
                combinado[n] = r
    return sorted(combinado.values(), key=lambda r: r.numero_pregunta)

def callback_ocr(
    ch: pika.adapters.blocking_connection.BlockingChannel,
    method: pika.spec.Basic.Deliver,
    properties: pika.spec.BasicProperties,
    body: bytes,
) -> None:
    pub_conn = None
    try:
        msg               = json.loads(body.decode("utf-8"))
        examen_id         = msg.get("examen_id")
        alumno_id         = msg.get("alumno_id")
        solucionario_id   = msg.get("solucionario_id")
        solucionario_data = msg.get("solucionario_data", {})
        imagenes          = msg.get("imagenes_procesadas", [])

        logger.info(
            f"📨 OCR iniciado: examen_id={examen_id} "
            f"alumno={alumno_id} imágenes={len(imagenes)}"
        )

        resultados_paginas = []
        for img_path in imagenes:
            if not os.path.exists(img_path):
                logger.warning(f"Imagen no encontrada: {img_path}. Omitida.")
                continue
            try:
                resultados_paginas.append(procesar_imagen_ocr(img_path))
            except Exception as e:
                logger.error(f"Error OCR en {img_path}: {e}")
                resultados_paginas.append([])

        resultados = combinar_paginas(resultados_paginas)

        logger.info(
            f"✅ OCR examen_id={examen_id}: "
            f"{len(resultados)} respuestas extraídas"
        )
        for r in resultados:
            tipo = "ALT" if r.es_alternativa else "TXT"
            logger.info(
                f"  P{r.numero_pregunta} [{tipo}]: "
                f"'{r.texto_extraido[:30]}' conf={r.confianza:.2f}"
            )

        pub_conn    = connect_with_retry()
        pub_channel = pub_conn.channel()
        declare_queues(pub_channel)

        publish_message(pub_channel, QUEUE_CALIFICACION, {
            "examen_id"        : examen_id,
            "alumno_id"        : alumno_id,
            "solucionario_id"  : solucionario_id,
            "solucionario_data": solucionario_data,
            "resultados_ocr"   : [
                {
                    "numero_pregunta": r.numero_pregunta,
                    "texto_extraido" : r.texto_extraido,
                    "confianza"      : r.confianza,
                    "es_alternativa" : r.es_alternativa,
                }
                for r in resultados
            ],
        })

        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("✔ Publicado en cola_calificacion.")

    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido: {e}. NACK sin requeue.")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.exception(f"Error inesperado: {e}. Reencolar.")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    finally:
        if pub_conn and not pub_conn.is_closed:
            pub_conn.close()

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT,  lambda s, f: sys.exit(0))

    logger.info("🚀 ms_ocr iniciando...")
    logger.info(f"  Tesseract : {TESSERACT_CMD}  Lang: {TESSERACT_LANG}")

    try:
        v = pytesseract.get_tesseract_version()
        logger.info(f"  Versión   : {v}")
    except Exception as e:
        logger.error(f"  Tesseract no encontrado: {e}")

    start_consumer(
        queue=QUEUE_OCR,
        callback=callback_ocr,
        prefetch_count=1,
    )