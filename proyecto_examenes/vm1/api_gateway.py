import base64
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import (
    Curso, Solucionario, Examen, RespuestaAlumno, Reporte,
    EstadoExamen, EstadoRespuesta,
    create_gateway_engine, init_gateway_db,
    create_calificacion_engine, init_calificacion_db,
    create_reporte_engine, init_reporte_db,
    get_session_factory,
)
from rabbitmq_config import (
    connect_with_retry, declare_queues, publish_message,
    QUEUE_PREPROCESAMIENTO, QUEUE_REPORTE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api_gateway")

engine_gw  = create_gateway_engine()
engine_cal = create_calificacion_engine()
engine_rep = create_reporte_engine()

SessionGW  = get_session_factory(engine_gw)
SessionCal = get_session_factory(engine_cal)
SessionRep = get_session_factory(engine_rep)

UPLOAD_DIR               = os.getenv("UPLOAD_DIR", "/tmp/examenes_uploads")
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.75"))
NOTA_APROBATORIA         = float(os.getenv("NOTA_APROBATORIA", "10.5"))

os.makedirs(UPLOAD_DIR, exist_ok=True)

_rmq_conn    = None
_rmq_channel = None

def get_rmq_channel():
    global _rmq_conn, _rmq_channel
    try:
        if _rmq_conn is None or _rmq_conn.is_closed:
            _rmq_conn    = connect_with_retry()
            _rmq_channel = _rmq_conn.channel()
            declare_queues(_rmq_channel)
    except Exception as e:
        logger.error(f"RabbitMQ error: {e}")
        raise
    return _rmq_channel

def get_db_gw():
    db = SessionGW()
    try:
        yield db
    finally:
        db.close()

def get_db_cal():
    db = SessionCal()
    try:
        yield db
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando API Gateway...")
    init_gateway_db(engine_gw)
    init_calificacion_db(engine_cal)
    init_reporte_db(engine_rep)
    get_rmq_channel()
    logger.info("✅ API Gateway listo.")
    yield
    if _rmq_conn and not _rmq_conn.is_closed:
        _rmq_conn.close()

app = FastAPI(
    title="Sistema de Evaluación Automática de Exámenes",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CursoCreate(BaseModel):
    nombre  : str            = Field(..., example="Biología General")
    seccion : str            = Field("A", example="A")
    periodo : str            = Field("2026-1", example="2026-1")
    docente : Optional[str]  = Field(None, example="Prof. García")
    color   : str            = Field("green", example="green")

class CursoUpdate(BaseModel):
    nombre  : Optional[str] = None
    seccion : Optional[str] = None
    periodo : Optional[str] = None
    docente : Optional[str] = None
    color   : Optional[str] = None

class SolucionarioCreate(BaseModel):
    curso_id                : int
    nombre                  : str
    descripcion             : Optional[str] = None
    respuestas              : dict  = Field(..., example={"1": "B", "2": "C"})
    puntaje_total           : float = Field(20.0, gt=0)
    puntaje_por_pregunta    : Optional[float] = None
    puntajes_individuales   : Optional[dict]  = Field(None, example={"1": 2.0, "9": 4.0})

class SolucionarioUpdate(BaseModel):
    nombre                  : Optional[str]   = None
    descripcion             : Optional[str]   = None
    respuestas              : Optional[dict]  = None
    puntaje_total           : Optional[float] = None
    puntaje_por_pregunta    : Optional[float] = None
    puntajes_individuales   : Optional[dict]  = None

class RevisionManualRequest(BaseModel):
    respuesta_corregida : str
    revisado_por        : Optional[str] = None
    observaciones       : Optional[str] = None

def _curso_dict(c: Curso) -> dict:
    return {
        "id"      : c.id,
        "nombre"  : c.nombre,
        "seccion" : c.seccion,
        "periodo" : c.periodo,
        "docente" : c.docente,
        "color"   : c.color,
    }

def _sol_dict(s: Solucionario) -> dict:
    return {
        "id"                   : s.id,
        "curso_id"             : s.curso_id,
        "nombre"               : s.nombre,
        "descripcion"          : s.descripcion,
        "respuestas"           : s.respuestas,
        "num_preguntas"        : len(s.respuestas) if s.respuestas else 0,
        "puntaje_total"        : s.puntaje_total,
        "puntaje_por_pregunta" : s.puntaje_por_pregunta,
        "puntajes_individuales": s.puntajes_individuales,
        "created_at"           : s.created_at.isoformat(),
    }

@app.get("/cursos", tags=["Cursos"])
def listar_cursos(db: Session = Depends(get_db_gw)):
    cursos = db.query(Curso).filter(Curso.activo == True).order_by(Curso.id).all()
    return [_curso_dict(c) for c in cursos]

@app.post("/cursos", status_code=201, tags=["Cursos"])
def crear_curso(payload: CursoCreate, db: Session = Depends(get_db_gw)):
    curso = Curso(**payload.model_dump())
    db.add(curso)
    db.commit()
    db.refresh(curso)
    logger.info(f"Curso creado: id={curso.id} nombre={curso.nombre}")
    return _curso_dict(curso)

@app.get("/cursos/{curso_id}", tags=["Cursos"])
def obtener_curso(curso_id: int, db: Session = Depends(get_db_gw)):
    curso = db.query(Curso).filter(Curso.id == curso_id, Curso.activo == True).first()
    if not curso:
        raise HTTPException(404, f"Curso id={curso_id} no encontrado")
    return _curso_dict(curso)

@app.patch("/cursos/{curso_id}", tags=["Cursos"])
def actualizar_curso(curso_id: int, payload: CursoUpdate,
                     db: Session = Depends(get_db_gw)):
    curso = db.query(Curso).filter(Curso.id == curso_id, Curso.activo == True).first()
    if not curso:
        raise HTTPException(404, f"Curso id={curso_id} no encontrado")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(curso, campo, valor)
    db.commit()
    db.refresh(curso)
    return _curso_dict(curso)

@app.delete("/cursos/{curso_id}", tags=["Cursos"])
def eliminar_curso(curso_id: int, db: Session = Depends(get_db_gw)):
    curso = db.query(Curso).filter(Curso.id == curso_id, Curso.activo == True).first()
    if not curso:
        raise HTTPException(404, f"Curso id={curso_id} no encontrado")
    curso.activo = False
    db.commit()
    return {"mensaje": f"Curso id={curso_id} eliminado"}

@app.get("/cursos/{curso_id}/solucionarios", tags=["Solucionarios"])
def listar_solucionarios_por_curso(curso_id: int, db: Session = Depends(get_db_gw)):
    curso = db.query(Curso).filter(Curso.id == curso_id, Curso.activo == True).first()
    if not curso:
        raise HTTPException(404, f"Curso id={curso_id} no encontrado")
    sols = db.query(Solucionario).filter(
        Solucionario.curso_id == curso_id,
        Solucionario.activo   == True,
    ).all()
    return [_sol_dict(s) for s in sols]

@app.get("/solucionarios", tags=["Solucionarios"])
def listar_todos_solucionarios(db: Session = Depends(get_db_gw)):
    return [_sol_dict(s) for s in
            db.query(Solucionario).filter(Solucionario.activo == True).all()]

@app.get("/solucionarios/{sol_id}", tags=["Solucionarios"])
def obtener_solucionario(sol_id: int, db: Session = Depends(get_db_gw)):
    sol = db.query(Solucionario).filter(
        Solucionario.id == sol_id, Solucionario.activo == True).first()
    if not sol:
        raise HTTPException(404, f"Solucionario id={sol_id} no encontrado")
    return _sol_dict(sol)

@app.post("/solucionario", status_code=201, tags=["Solucionarios"])
def crear_solucionario(payload: SolucionarioCreate, db: Session = Depends(get_db_gw)):
    curso = db.query(Curso).filter(
        Curso.id == payload.curso_id, Curso.activo == True).first()
    if not curso:
        raise HTTPException(404, f"Curso id={payload.curso_id} no encontrado")

    if payload.puntajes_individuales:
        suma = sum(float(v) for v in payload.puntajes_individuales.values())
        if round(suma, 2) != round(payload.puntaje_total, 2):
            raise HTTPException(
                400,
                f"Suma de puntajes_individuales ({suma}) "
                f"≠ puntaje_total ({payload.puntaje_total})",
            )
        sin_puntaje = [
            k for k in payload.respuestas
            if str(k) not in {str(p) for p in payload.puntajes_individuales}
        ]
        if sin_puntaje:
            raise HTTPException(400, f"Preguntas sin puntaje definido: {sin_puntaje}")

    sol = Solucionario(**payload.model_dump())
    db.add(sol)
    db.commit()
    db.refresh(sol)
    logger.info(f"Solucionario creado: id={sol.id} curso={sol.curso_id}")
    return _sol_dict(sol)

@app.patch("/solucionarios/{sol_id}", tags=["Solucionarios"])
def actualizar_solucionario(sol_id: int, payload: SolucionarioUpdate,
                            db: Session = Depends(get_db_gw)):
    sol = db.query(Solucionario).filter(
        Solucionario.id == sol_id, Solucionario.activo == True).first()
    if not sol:
        raise HTTPException(404, f"Solucionario id={sol_id} no encontrado")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(sol, campo, valor)
    db.commit()
    db.refresh(sol)
    return _sol_dict(sol)

@app.delete("/solucionarios/{sol_id}", tags=["Solucionarios"])
def eliminar_solucionario(sol_id: int, db: Session = Depends(get_db_gw)):
    sol = db.query(Solucionario).filter(
        Solucionario.id == sol_id, Solucionario.activo == True).first()
    if not sol:
        raise HTTPException(404, f"Solucionario id={sol_id} no encontrado")
    sol.activo = False
    db.commit()
    return {"mensaje": f"Solucionario id={sol_id} eliminado"}

@app.post("/examenes/subir", status_code=202, tags=["Exámenes"])
async def subir_examenes(
    solucionario_id : int              = Form(...),
    alumno_ids      : str              = Form(...),
    alumno_nombres  : Optional[str]    = Form(None),
    archivos        : List[UploadFile] = File(...),
    db_gw           : Session          = Depends(get_db_gw),
    db_cal          : Session          = Depends(get_db_cal),
):
    sol = db_gw.query(Solucionario).filter(
        Solucionario.id == solucionario_id,
        Solucionario.activo == True,
    ).first()
    if not sol:
        raise HTTPException(404, f"Solucionario id={solucionario_id} no encontrado")

    ids_lista     = [i.strip() for i in alumno_ids.split(",")]
    nombres_lista = [n.strip() for n in alumno_nombres.split(",")] if alumno_nombres else []

    if len(archivos) != len(ids_lista):
        raise HTTPException(
            400,
            f"Archivos ({len(archivos)}) ≠ alumno_ids ({len(ids_lista)})",
        )

    channel      = get_rmq_channel()
    examenes_creados = []

    for idx, (archivo, alumno_id) in enumerate(zip(archivos, ids_lista)):
        nombre_alumno = nombres_lista[idx] if idx < len(nombres_lista) else None
        ext           = os.path.splitext(archivo.filename)[1].lower()
        nombre_unico  = f"{uuid.uuid4()}{ext}"
        contenido     = await archivo.read()
        contenido_b64 = base64.b64encode(contenido).decode("utf-8")

        with open(os.path.join(UPLOAD_DIR, nombre_unico), "wb") as f:
            f.write(contenido)

        examen = Examen(
            alumno_id       = alumno_id,
            alumno_nombre   = nombre_alumno,
            solucionario_id = solucionario_id,
            curso_id        = sol.curso_id,
            archivo_original= nombre_unico,
            estado          = EstadoExamen.PREPROCESANDO,
        )
        db_cal.add(examen)
        db_cal.commit()
        db_cal.refresh(examen)

        publish_message(channel, QUEUE_PREPROCESAMIENTO, {
            "examen_id"        : examen.id,
            "alumno_id"        : alumno_id,
            "solucionario_id"  : solucionario_id,
            "nombre_archivo"   : nombre_unico,
            "tipo_archivo"     : ext.lstrip("."),
            "contenido_base64" : contenido_b64,
            "solucionario_data": {
                "respuestas"           : sol.respuestas,
                "puntaje_total"        : sol.puntaje_total,
                "puntaje_por_pregunta" : sol.puntaje_por_pregunta,
                "puntajes_individuales": sol.puntajes_individuales,
            },
        })

        examenes_creados.append({
            "examen_id"    : examen.id,
            "alumno_id"    : alumno_id,
            "alumno_nombre": nombre_alumno,
            "estado"       : examen.estado.value,
        })
        logger.info(f"Examen id={examen.id} enviado a preprocesamiento.")

    return {
        "mensaje"         : f"{len(examenes_creados)} exámenes enviados al pipeline.",
        "examenes_creados": examenes_creados,
    }

@app.get("/examenes/{examen_id}/estado", tags=["Exámenes"])
def obtener_estado_examen(examen_id: int, db: Session = Depends(get_db_cal)):
    examen = db.query(Examen).filter(Examen.id == examen_id).first()
    if not examen:
        raise HTTPException(404, f"Examen id={examen_id} no encontrado")
    pendientes = db.query(RespuestaAlumno).filter(
        RespuestaAlumno.examen_id == examen_id,
        RespuestaAlumno.estado    == EstadoRespuesta.PENDIENTE_REVISION,
    ).count()
    return {
        "id"                   : examen.id,
        "alumno_id"            : examen.alumno_id,
        "alumno_nombre"        : examen.alumno_nombre,
        "estado"               : examen.estado.value,
        "nota_final"           : examen.nota_final,
        "porcentaje_aciertos"  : examen.porcentaje_aciertos,
        "respuestas_pendientes": pendientes,
    }

@app.get("/examenes/{examen_id}/respuestas", tags=["Exámenes"])
def obtener_respuestas_examen(examen_id: int, db: Session = Depends(get_db_cal)):
    examen = db.query(Examen).filter(Examen.id == examen_id).first()
    if not examen:
        raise HTTPException(404, f"Examen id={examen_id} no encontrado")
    respuestas = (
        db.query(RespuestaAlumno)
        .filter(RespuestaAlumno.examen_id == examen_id)
        .order_by(RespuestaAlumno.numero_pregunta)
        .all()
    )
    return {
        "examen_id"    : examen_id,
        "alumno_id"    : examen.alumno_id,
        "alumno_nombre": examen.alumno_nombre,
        "estado_examen": examen.estado.value,
        "nota_final"   : examen.nota_final,
        "respuestas"   : [
            {
                "id"                : r.id,
                "numero_pregunta"   : r.numero_pregunta,
                "respuesta_ocr"     : r.respuesta_ocr,
                "confianza_ocr"     : r.confianza_ocr,
                "respuesta_correcta": r.respuesta_correcta,
                "respuesta_manual"  : r.respuesta_manual,
                "es_correcta"       : r.es_correcta,
                "estado"            : r.estado.value,
                "observaciones"     : r.observaciones,
            }
            for r in respuestas
        ],
    }

@app.get("/revision/pendientes", tags=["Revisión Manual"])
def listar_pendientes(db: Session = Depends(get_db_cal)):
    pendientes = (
        db.query(RespuestaAlumno)
        .filter(RespuestaAlumno.estado == EstadoRespuesta.PENDIENTE_REVISION)
        .join(Examen)
        .order_by(RespuestaAlumno.examen_id, RespuestaAlumno.numero_pregunta)
        .all()
    )
    return {
        "total_pendientes": len(pendientes),
        "items": [
            {
                "respuesta_id"      : r.id,
                "examen_id"         : r.examen_id,
                "alumno_id"         : r.examen.alumno_id,
                "alumno_nombre"     : r.examen.alumno_nombre,
                "numero_pregunta"   : r.numero_pregunta,
                "respuesta_ocr"     : r.respuesta_ocr,
                "confianza_ocr"     : r.confianza_ocr,
                "respuesta_correcta": r.respuesta_correcta,
            }
            for r in pendientes
        ],
    }

@app.patch("/revision/{respuesta_id}", tags=["Revisión Manual"])
def revisar_respuesta(
    respuesta_id : int,
    payload      : RevisionManualRequest,
    db_cal       : Session = Depends(get_db_cal),
    db_gw        : Session = Depends(get_db_gw),
):
    respuesta = db_cal.query(RespuestaAlumno).filter(
        RespuestaAlumno.id == respuesta_id).first()
    if not respuesta:
        raise HTTPException(404, f"Respuesta id={respuesta_id} no encontrada")
    if respuesta.estado != EstadoRespuesta.PENDIENTE_REVISION:
        raise HTTPException(
            400,
            f"Respuesta no está pendiente (estado: {respuesta.estado})",
        )

    respuesta.respuesta_manual = payload.respuesta_corregida.strip().upper()
    respuesta.revisado_por     = payload.revisado_por
    respuesta.observaciones    = payload.observaciones
    respuesta.estado           = EstadoRespuesta.REVISADA
    resp_correcta              = (respuesta.respuesta_correcta or "").strip().upper()
    respuesta.es_correcta      = (respuesta.respuesta_manual == resp_correcta)
    db_cal.commit()

    examen = db_cal.query(Examen).filter(Examen.id == respuesta.examen_id).first()
    pendientes_restantes = db_cal.query(RespuestaAlumno).filter(
        RespuestaAlumno.examen_id == examen.id,
        RespuestaAlumno.estado    == EstadoRespuesta.PENDIENTE_REVISION,
    ).count()

    if pendientes_restantes == 0:
        sol = db_gw.query(Solucionario).filter(
            Solucionario.id == examen.solucionario_id).first()
        if sol:
            _recalcular_nota(examen, db_cal, sol)
        examen.estado = EstadoExamen.REVISION_COMPLETA
        db_cal.commit()

    return {
        "mensaje"             : "Respuesta corregida.",
        "respuesta_id"        : respuesta_id,
        "es_correcta"         : respuesta.es_correcta,
        "pendientes_en_examen": pendientes_restantes,
        "nota_final_examen"   : examen.nota_final,
    }

def _recalcular_nota(examen: Examen, db: Session, sol: Solucionario) -> None:
    respuestas      = db.query(RespuestaAlumno).filter(
        RespuestaAlumno.examen_id == examen.id).all()
    total_preguntas = len(sol.respuestas)
    if total_preguntas == 0:
        return
    correctas    = sum(1 for r in respuestas if r.es_correcta)
    puntajes_ind = sol.puntajes_individuales or {}
    if puntajes_ind:
        nota = sum(
            float(puntajes_ind.get(str(r.numero_pregunta), 0.0))
            for r in respuestas if r.es_correcta
        )
    else:
        ppu  = sol.puntaje_por_pregunta or sol.puntaje_total / total_preguntas
        nota = correctas * ppu
    examen.nota_final           = round(nota, 2)
    examen.porcentaje_aciertos = round((correctas / total_preguntas) * 100, 2)

@app.post("/reportes/generar", status_code=202, tags=["Reportes"])
def solicitar_reporte(
    solucionario_id : Optional[int] = None,
    curso_id        : Optional[int] = None,
    nombre_reporte  : str           = "Reporte General",
):
    channel = get_rmq_channel()
    publish_message(channel, QUEUE_REPORTE, {
        "solucionario_id": solucionario_id,
        "curso_id"       : curso_id,
        "nombre_reporte" : nombre_reporte,
        "solicitud_id"   : str(uuid.uuid4()),
    })
    return {"mensaje": "Solicitud de reporte enviada."}

@app.get("/reportes", tags=["Reportes"])
def listar_reportes():
    with SessionRep() as s:
        reportes = s.query(Reporte).order_by(Reporte.created_at.desc()).all()
        return [
            {
                "id"             : r.id,
                "nombre"         : r.nombre,
                "solucionario_id": r.solucionario_id,
                "curso_id"       : r.curso_id,
                "total_examenes" : r.total_examenes,
                "promedio_notas" : r.promedio_notas,
                "aprobados"      : r.aprobados,
                "desaprobados"   : r.desaprobados,
                "created_at"     : r.created_at.isoformat(),
            }
            for r in reportes
        ]

@app.get("/reportes/solucionario/{solucionario_id}/directo", tags=["Reportes"])
def reporte_directo(
    solucionario_id: int,
    db_cal: Session = Depends(get_db_cal),
    db_gw : Session = Depends(get_db_gw),
):
    sol = db_gw.query(Solucionario).filter(
        Solucionario.id == solucionario_id).first()
    if not sol:
        raise HTTPException(404, f"Solucionario id={solucionario_id} no encontrado")

    examenes = db_cal.query(Examen).filter(
        Examen.solucionario_id == solucionario_id
    ).order_by(Examen.alumno_id).all()

    notas    = [e.nota_final for e in examenes if e.nota_final is not None]
    promedio = round(sum(notas) / len(notas), 2) if notas else None
    aprobados = sum(1 for n in notas if n >= NOTA_APROBATORIA)

    return {
        "solucionario"        : {"id": sol.id, "nombre": sol.nombre},
        "total_examenes"      : len(examenes),
        "calificados"         : len(notas),
        "pendientes_revision" : sum(
            1 for e in examenes if e.estado == EstadoExamen.PENDIENTE_REVISION
        ),
        "promedio_notas"      : promedio,
        "nota_minima"         : min(notas) if notas else None,
        "nota_maxima"         : max(notas) if notas else None,
        "aprobados"           : aprobados,
        "desaprobados"        : len(notas) - aprobados,
        "detalle_alumnos"     : [
            {
                "examen_id"          : e.id,
                "alumno_id"          : e.alumno_id,
                "alumno_nombre"      : e.alumno_nombre,
                "nota_final"         : e.nota_final,
                "porcentaje_aciertos": e.porcentaje_aciertos,
                "estado_examen"      : e.estado.value,
                "aprobado"           : (
                    e.nota_final >= NOTA_APROBATORIA if e.nota_final is not None else None
                ),
                "archivo_original"   : e.archivo_original,
            }
            for e in examenes
        ],
    }

@app.get("/health", tags=["Sistema"])
def health_check(db: Session = Depends(get_db_gw)):
    db_gw_ok = db_cal_ok = db_rep_ok = rmq_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_gw_ok = True
    except Exception:
        pass
    try:
        s = SessionCal()
        s.execute(text("SELECT 1"))
        s.close()
        db_cal_ok = True
    except Exception:
        pass
    try:
        s = SessionRep()
        s.execute(text("SELECT 1"))
        s.close()
        db_rep_ok = True
    except Exception:
        pass
    try:
        rmq_ok = get_rmq_channel().is_open
    except Exception:
        pass

    status = "ok" if all([db_gw_ok, db_cal_ok, db_rep_ok, rmq_ok]) else "degraded"
    return {
        "status"          : status,
        "bd_gateway"      : "ok" if db_gw_ok  else "error",
        "bd_calificacion" : "ok" if db_cal_ok else "error",
        "bd_reporte"      : "ok" if db_rep_ok else "error",
        "rabbitmq"        : "ok" if rmq_ok    else "error",
        "version"         : "2.0.0",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_gateway:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", 8000)),
        reload=False,
    )