import enum
import logging
import os
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text,
    Enum as SAEnum, create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

logger = logging.getLogger(__name__)

BaseGateway      = declarative_base()
BaseCalificacion = declarative_base()
BaseReporte      = declarative_base()

def _url(db_env: str, default: str) -> str:
    return (
        f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'admin123')}@"
        f"{os.getenv('POSTGRES_HOST', 'postgres')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv(db_env, default)}"
    )

def get_gateway_url()     -> str: return _url("POSTGRES_DB_GATEWAY",     "bd_gateway")
def get_calificacion_url() -> str: return _url("POSTGRES_DB_CALIFICACION",  "bd_calificacion")
def get_reporte_url()      -> str: return _url("POSTGRES_DB_REPORTE",       "bd_reporte")

class EstadoRespuesta(str, enum.Enum):
    PENDIENTE_REVISION = "pendiente_revision"
    REVISADA           = "revisada"
    PROCESADA          = "procesada"

class EstadoExamen(str, enum.Enum):
    RECIBIDO           = "recibido"
    PREPROCESANDO      = "preprocesando"
    OCR_COMPLETADO     = "ocr_completado"
    CALIFICADO         = "calificado"
    PENDIENTE_REVISION = "pendiente_revision"
    REVISION_COMPLETA  = "revision_completa"

class Curso(BaseGateway):
    __tablename__ = "cursos"

    id         = Column(Integer, primary_key=True, index=True)
    nombre     = Column(String(255), nullable=False)
    seccion    = Column(String(20),  nullable=False, default="A")
    periodo    = Column(String(20),  nullable=False, default="2026-1")
    docente    = Column(String(255), nullable=True)
    color      = Column(String(30),  nullable=False, default="green")
    activo     = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    solucionarios = relationship("Solucionario", back_populates="curso",
                                 cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Curso id={self.id} nombre={self.nombre}>"

class Solucionario(BaseGateway):
    __tablename__ = "solucionarios"

    id                    = Column(Integer, primary_key=True, index=True)
    curso_id              = Column(Integer, ForeignKey("cursos.id"), nullable=False)
    nombre                = Column(String(255), nullable=False)
    descripcion           = Column(Text, nullable=True)
    respuestas            = Column(JSON, nullable=False)
    puntaje_total         = Column(Float, default=20.0)
    puntaje_por_pregunta  = Column(Float, nullable=True)
    puntajes_individuales = Column(JSON, nullable=True)
    activo                = Column(Boolean, default=True)
    created_at            = Column(DateTime, default=datetime.utcnow)

    curso = relationship("Curso", back_populates="solucionarios")

    def __repr__(self):
        return f"<Solucionario id={self.id} nombre={self.nombre}>"

class Examen(BaseCalificacion):
    __tablename__ = "examenes"

    id                  = Column(Integer, primary_key=True, index=True)
    alumno_id           = Column(String(100), nullable=False, index=True)
    alumno_nombre       = Column(String(255), nullable=True)
    solucionario_id     = Column(Integer, nullable=False, index=True)
    curso_id            = Column(Integer, nullable=True,  index=True)
    archivo_original    = Column(String(500), nullable=True)
    estado              = Column(SAEnum(EstadoExamen), default=EstadoExamen.RECIBIDO)
    nota_final          = Column(Float, nullable=True)
    porcentaje_aciertos = Column(Float, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    respuestas = relationship("RespuestaAlumno", back_populates="examen",
                              cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Examen id={self.id} alumno={self.alumno_id} estado={self.estado}>"

class RespuestaAlumno(BaseCalificacion):
    __tablename__ = "respuestas_alumno"

    id                 = Column(Integer, primary_key=True, index=True)
    examen_id          = Column(Integer, ForeignKey("examenes.id"), nullable=False)
    numero_pregunta    = Column(Integer, nullable=False)
    respuesta_ocr      = Column(String(500), nullable=True)
    confianza_ocr      = Column(Float, nullable=True)
    respuesta_correcta = Column(String(500), nullable=True)
    respuesta_manual   = Column(String(500), nullable=True)
    es_correcta        = Column(Boolean, nullable=True)
    estado             = Column(SAEnum(EstadoRespuesta), default=EstadoRespuesta.PROCESADA)
    observaciones      = Column(Text, nullable=True)
    revisado_por       = Column(String(100), nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    examen = relationship("Examen", back_populates="respuestas")

    def __repr__(self):
        return f"<Respuesta examen={self.examen_id} p={self.numero_pregunta}>"

class Reporte(BaseReporte):
    __tablename__ = "reportes"

    id              = Column(Integer, primary_key=True, index=True)
    solucionario_id = Column(Integer, nullable=True, index=True)
    curso_id        = Column(Integer, nullable=True, index=True)
    nombre          = Column(String(255), nullable=False)
    datos_reporte   = Column(JSON, nullable=False)
    total_examenes  = Column(Integer, default=0)
    promedio_notas  = Column(Float, nullable=True)
    aprobados       = Column(Integer, default=0)
    desaprobados    = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Reporte id={self.id} nombre={self.nombre}>"

def _make_engine(url: str):
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
    )

def create_gateway_engine():      return _make_engine(get_gateway_url())
def create_calificacion_engine(): return _make_engine(get_calificacion_url())
def create_reporte_engine():      return _make_engine(get_reporte_url())

def init_gateway_db(engine) -> None:
    BaseGateway.metadata.create_all(bind=engine)
    logger.info("bd_gateway — tablas inicializadas")

def init_calificacion_db(engine) -> None:
    BaseCalificacion.metadata.create_all(bind=engine)
    logger.info("bd_calificacion — tablas inicializadas")

def init_reporte_db(engine) -> None:
    BaseReporte.metadata.create_all(bind=engine)
    logger.info("bd_reporte — tablas inicializadas")

def get_session_factory(engine) -> sessionmaker:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)