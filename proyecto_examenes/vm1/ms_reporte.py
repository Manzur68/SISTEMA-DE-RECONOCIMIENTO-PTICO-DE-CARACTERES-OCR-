import json
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional

import pika
from sqlalchemy.orm import Session

from database import (
    Examen, RespuestaAlumno, Reporte, EstadoExamen, EstadoRespuesta,
    create_calificacion_engine, init_calificacion_db,
    create_reporte_engine,     init_reporte_db,
    get_session_factory,
)
from rabbitmq_config import start_consumer, QUEUE_REPORTE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ms_reporte")

NOTA_APROBATORIA = float(os.getenv("NOTA_APROBATORIA", "10.5"))

engine_cal = create_calificacion_engine()
engine_rep = create_reporte_engine()

SessionCal = get_session_factory(engine_cal)
SessionRep = get_session_factory(engine_rep)

def generar_reporte(
    solucionario_id: Optional[int],
    curso_id       : Optional[int],
    nombre_reporte : str,
    solicitud_id   : str,
    db_cal         : Session,
) -> Dict:

    query = db_cal.query(Examen)
    if solucionario_id:
        query = query.filter(Examen.solucionario_id == solucionario_id)
    if curso_id:
        query = query.filter(Examen.curso_id == curso_id)
    examenes = query.order_by(Examen.alumno_id).all()

    notas       = [e.nota_final for e in examenes if e.nota_final is not None]
    promedio    = round(sum(notas) / len(notas), 2) if notas else None
    aprobados   = sum(1 for n in notas if n >= NOTA_APROBATORIA)
    desv        = None
    if len(notas) > 1:
        media = sum(notas) / len(notas)
        desv  = round((sum((n - media) ** 2 for n in notas) / len(notas)) ** 0.5, 2)

    todas_respuestas = []
    for e in examenes:
        todas_respuestas.extend(
            db_cal.query(RespuestaAlumno)
            .filter(RespuestaAlumno.examen_id == e.id)
            .all()
        )

    stats_preg: Dict[int, Dict] = {}
    for r in todas_respuestas:
        n = r.numero_pregunta
        if n not in stats_preg:
            stats_preg[n] = {
                "numero_pregunta": n,
                "total"          : 0,
                "correctas"      : 0,
                "incorrectas"    : 0,
                "pendientes"     : 0,
            }
        stats_preg[n]["total"] += 1
        if r.estado == EstadoRespuesta.PENDIENTE_REVISION:
            stats_preg[n]["pendientes"] += 1
        elif r.es_correcta:
            stats_preg[n]["correctas"] += 1
        else:
            stats_preg[n]["incorrectas"] += 1

    for d in stats_preg.values():
        den = d["correctas"] + d["incorrectas"]
        d["porcentaje_acierto"] = round(d["correctas"] / den * 100, 2) if den else 0.0

    detalle_alumnos = []
    for e in examenes:
        resps = (
            db_cal.query(RespuestaAlumno)
            .filter(RespuestaAlumno.examen_id == e.id)
            .order_by(RespuestaAlumno.numero_pregunta)
            .all()
        )
        detalle_alumnos.append({
            "examen_id"          : e.id,
            "alumno_id"          : e.alumno_id,
            "alumno_nombre"      : e.alumno_nombre or "Sin nombre",
            "nota_final"         : e.nota_final,
            "porcentaje_aciertos": e.porcentaje_aciertos,
            "estado_examen"      : e.estado.value,
            "aprobado"           : (
                e.nota_final >= NOTA_APROBATORIA
                if e.nota_final is not None else None
            ),
            "respuestas": [
                {
                    "numero_pregunta"   : r.numero_pregunta,
                    "respuesta_final"   : r.respuesta_manual or r.respuesta_ocr,
                    "respuesta_correcta": r.respuesta_correcta,
                    "es_correcta"       : r.es_correcta,
                    "estado"            : r.estado.value,
                    "confianza_ocr"     : r.confianza_ocr,
                }
                for r in resps
            ],
        })

    return {
        "metadata": {
            "solicitud_id"    : solicitud_id,
            "nombre_reporte"  : nombre_reporte,
            "fecha_generacion": datetime.utcnow().isoformat(),
            "solucionario_id" : solucionario_id,
            "curso_id"        : curso_id,
        },
        "resumen": {
            "total_examenes"      : len(examenes),
            "examenes_calificados": len(notas),
            "pendientes_revision" : sum(
                1 for e in examenes
                if e.estado == EstadoExamen.PENDIENTE_REVISION
            ),
            "promedio_notas"      : promedio,
            "nota_minima"         : min(notas) if notas else None,
            "nota_maxima"         : max(notas) if notas else None,
            "desviacion_estandar" : desv,
            "aprobados"           : aprobados,
            "desaprobados"        : len(notas) - aprobados,
            "porcentaje_aprobacion": round(aprobados / len(notas) * 100, 2) if notas else 0,
            "nota_aprobatoria"    : NOTA_APROBATORIA,
        },
        "estadisticas_preguntas": sorted(
            stats_preg.values(), key=lambda x: x["numero_pregunta"]
        ),
        "detalle_alumnos": detalle_alumnos,
    }

def callback_reporte(
    ch: pika.adapters.blocking_connection.BlockingChannel,
    method: pika.spec.Basic.Deliver,
    properties: pika.spec.BasicProperties,
    body: bytes,
) -> None:
    db_cal = SessionCal()
    db_rep = SessionRep()
    try:
        msg             = json.loads(body.decode("utf-8"))
        solucionario_id = msg.get("solucionario_id")
        curso_id        = msg.get("curso_id")
        nombre_reporte  = msg.get("nombre_reporte", "Reporte de Notas")
        solicitud_id    = msg.get("solicitud_id", "sin-id")

        logger.info(
            f"📨 Generando reporte '{nombre_reporte}' "
            f"(sol={solucionario_id} curso={curso_id})"
        )

        datos   = generar_reporte(solucionario_id, curso_id,
                                  nombre_reporte, solicitud_id, db_cal)
        resumen = datos["resumen"]

        rep = Reporte(
            solucionario_id = solucionario_id,
            curso_id        = curso_id,
            nombre          = nombre_reporte,
            datos_reporte   = datos,
            total_examenes  = resumen["total_examenes"],
            promedio_notas  = resumen["promedio_notas"],
            aprobados       = resumen["aprobados"],
            desaprobados    = resumen["desaprobados"],
        )
        db_rep.add(rep)
        db_rep.commit()
        logger.info(f"✅ Reporte id={rep.id} guardado en bd_reporte")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.exception(f"Error generando reporte: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    finally:
        db_cal.close()
        db_rep.close()

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT,  lambda s, f: sys.exit(0))

    logger.info("🚀 ms_reporte iniciando...")
    logger.info(f"  Lee de  : bd_calificacion")
    logger.info(f"  Escribe : bd_reporte")

    init_calificacion_db(engine_cal)
    init_reporte_db(engine_rep)

    start_consumer(
        queue=QUEUE_REPORTE,
        callback=callback_reporte,
        prefetch_count=1,
    )