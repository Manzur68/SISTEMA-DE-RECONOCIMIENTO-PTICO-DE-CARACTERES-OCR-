import json
import logging
import os
import signal
import sys
from typing import Dict, List, Tuple

import pika
from sqlalchemy.orm import Session

from database import (
    Examen, RespuestaAlumno, EstadoExamen, EstadoRespuesta,
    create_calificacion_engine, init_calificacion_db, get_session_factory,
)
from rabbitmq_config import start_consumer, QUEUE_CALIFICACION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ms_calificacion")

OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.75"))
NOTA_APROBATORIA         = float(os.getenv("NOTA_APROBATORIA", "10.5"))

engine       = create_calificacion_engine()
SessionLocal = get_session_factory(engine)

def normalizar(texto: str) -> str:
    return texto.strip().upper().strip(".,;:!?") if texto else ""

def son_equivalentes(resp_alumno: str, resp_correcta: str) -> bool:
    r1, r2 = normalizar(resp_alumno), normalizar(resp_correcta)
    if not r1 or not r2:
        return False
    if r1 == r2:
        return True
    palabras_clave = set(r2.split())
    if len(palabras_clave) > 1 and len(r1) > 3:
        coincidencias = palabras_clave & set(r1.split())
        return len(coincidencias) / len(palabras_clave) >= 0.70
    return False

def calcular_nota(
    respuestas_evaluadas: List[Dict],
    sol_data: Dict,
) -> Tuple[float, float]:
    total_preguntas = len(sol_data.get("respuestas", {}))
    if total_preguntas == 0:
        return 0.0, 0.0

    contables = [
        r for r in respuestas_evaluadas
        if r["estado"] != EstadoRespuesta.PENDIENTE_REVISION.value
    ]

    puntajes_ind  = sol_data.get("puntajes_individuales") or {}
    puntaje_total = float(sol_data.get("puntaje_total", 20.0))

    if puntajes_ind:
        nota = sum(
            float(puntajes_ind.get(str(r["numero_pregunta"]), 0.0))
            for r in contables if r.get("es_correcta")
        )
    else:
        ppu  = float(sol_data.get("puntaje_por_pregunta") or puntaje_total / total_preguntas)
        nota = sum(ppu for r in contables if r.get("es_correcta"))

    correctas  = sum(1 for r in contables if r.get("es_correcta"))
    porcentaje = round((correctas / total_preguntas) * 100, 2)
    return round(nota, 2), porcentaje

def procesar_resultados_ocr(mensaje: Dict, db: Session) -> None:
    examen_id  = mensaje.get("examen_id")
    sol_data   = mensaje.get("solucionario_data", {})
    resultados = mensaje.get("resultados_ocr", [])

    logger.info(
        f"Calificando examen_id={examen_id} | "
        f"alumno={mensaje.get('alumno_id')} | "
        f"preguntas_ocr={len(resultados)}"
    )

    examen = db.query(Examen).filter(Examen.id == examen_id).first()
    if not examen:
        logger.error(f"Examen id={examen_id} no encontrado en bd_calificacion")
        return

    examen.estado = EstadoExamen.OCR_COMPLETADO
    db.commit()

    respuestas_correctas: Dict = sol_data.get("respuestas", {})
    hay_pendientes = False
    evaluadas      = []

    for res in resultados:
        num_preg  = str(res.get("numero_pregunta", ""))
        texto_ocr = res.get("texto_extraido", "")
        confianza = float(res.get("confianza", 0.0))
        correcta  = respuestas_correctas.get(num_preg, "")

        if confianza < OCR_CONFIDENCE_THRESHOLD or not texto_ocr:
            estado       = EstadoRespuesta.PENDIENTE_REVISION
            es_correcta = None
            hay_pendientes = True
            logger.warning(
                f"  P{num_preg}: confianza={confianza:.2f} < umbral={OCR_CONFIDENCE_THRESHOLD} "
                f"→ pendiente_revision"
            )
        else:
            estado       = EstadoRespuesta.PROCESADA
            es_correcta = son_equivalentes(texto_ocr, correcta)
            logger.debug(
                f"  P{num_preg}: ocr='{texto_ocr}' | correcta='{correcta}' | ok={es_correcta}"
            )

        db.add(RespuestaAlumno(
            examen_id         = examen_id,
            numero_pregunta   = int(num_preg) if num_preg.isdigit() else 0,
            respuesta_ocr     = texto_ocr,
            confianza_ocr     = confianza,
            respuesta_correcta= correcta,
            es_correcta       = es_correcta,
            estado            = estado,
        ))
        evaluadas.append({
            "numero_pregunta": num_preg,
            "es_correcta"    : es_correcta,
            "estado"         : estado.value,
        })

    db.commit()

    nota, porcentaje            = calcular_nota(evaluadas, sol_data)
    examen.nota_final           = nota
    examen.porcentaje_aciertos = porcentaje
    examen.estado = (
        EstadoExamen.PENDIENTE_REVISION if hay_pendientes
        else EstadoExamen.CALIFICADO
    )
    db.commit()

    estado_str = "PENDIENTE_REVISION" if hay_pendientes else (
        "APROBADO" if nota >= NOTA_APROBATORIA else "DESAPROBADO"
    )
    logger.info(
        f"✅ Examen id={examen_id} calificado | "
        f"Nota: {nota}/{sol_data.get('puntaje_total', 20)} | {estado_str}"
    )

def callback_calificacion(
    ch: pika.adapters.blocking_connection.BlockingChannel,
    method: pika.spec.Basic.Deliver,
    properties: pika.spec.BasicProperties,
    body: bytes,
) -> None:
    db = SessionLocal()
    try:
        mensaje = json.loads(body.decode("utf-8"))
        logger.info(f"📨 Mensaje recibido | examen_id={mensaje.get('examen_id')}")
        procesar_resultados_ocr(mensaje, db)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(f"✔ ACK enviado | examen_id={mensaje.get('examen_id')}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido: {e}. NACK sin requeue.")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.exception(f"Error inesperado: {e}. Reencolar.")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    finally:
        db.close()

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT,  lambda s, f: sys.exit(0))

    logger.info("🚀 ms_calificacion iniciando...")
    logger.info(f"  BD           : bd_calificacion")
    logger.info(f"  Umbral OCR   : {OCR_CONFIDENCE_THRESHOLD}")
    logger.info(f"  Aprobatoria : {NOTA_APROBATORIA}")

    init_calificacion_db(engine)
    start_consumer(
        queue=QUEUE_CALIFICACION,
        callback=callback_calificacion,
        prefetch_count=1,
    )