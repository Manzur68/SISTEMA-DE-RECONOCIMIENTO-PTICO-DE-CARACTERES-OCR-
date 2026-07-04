import json
import time
import pytest
import pika
import threading
from datetime import datetime
from typing import Generator

from testcontainers.postgres import PostgresContainer
from testcontainers.rabbitmq import RabbitMqContainer

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../vm1"))

from database import (
    BaseGateway, BaseCalificacion, BaseReporte,
    Curso, Solucionario, Examen, RespuestaAlumno, Reporte,
    EstadoExamen, EstadoRespuesta,
    get_session_factory,
)
from ms_calificacion import (
    normalizar, son_equivalentes, calcular_nota,
    procesar_resultados_ocr,
)
from ms_reporte import generar_reporte

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        pg.get_connection_url()
        yield pg

@pytest.fixture(scope="session")
def rabbitmq_container():
    with RabbitMqContainer("rabbitmq:3.13-management-alpine") as rmq:
        yield rmq

@pytest.fixture(scope="session")
def engines(postgres_container):
    base_url = postgres_container.get_connection_url()
    root_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with root_engine.connect() as conn:
        for db in ("bd_gateway", "bd_calificacion", "bd_reporte"):
            conn.execute(text(f"CREATE DATABASE {db}"))

    url_base = base_url.rsplit("/", 1)[0]

    engine_gw  = create_engine(f"{url_base}/bd_gateway")
    engine_cal = create_engine(f"{url_base}/bd_calificacion")
    engine_rep = create_engine(f"{url_base}/bd_reporte")

    BaseGateway.metadata.create_all(engine_gw)
    BaseCalificacion.metadata.create_all(engine_cal)
    BaseReporte.metadata.create_all(engine_rep)

    yield engine_gw, engine_cal, engine_rep

    engine_gw.dispose()
    engine_cal.dispose()
    engine_rep.dispose()

@pytest.fixture
def sessions(engines):
    engine_gw, engine_cal, engine_rep = engines
    session_gw  = get_session_factory(engine_gw)()
    session_cal = get_session_factory(engine_cal)()
    session_rep = get_session_factory(engine_rep)()

    yield session_gw, session_cal, session_rep

    session_gw.rollback(); session_gw.close()
    session_cal.rollback(); session_cal.close()
    session_rep.rollback(); session_rep.close()

@pytest.fixture
def rmq_channel(rabbitmq_container):
    params = pika.ConnectionParameters(
        host=rabbitmq_container.get_container_host_ip(),
        port=rabbitmq_container.get_exposed_port(5672),
        credentials=pika.PlainCredentials("guest", "guest"),
    )
    conn    = pika.BlockingConnection(params)
    channel = conn.channel()
    for queue in ["cola_preprocesamiento", "cola_ocr",
                  "cola_calificacion", "cola_reporte"]:
        channel.queue_declare(queue=queue, durable=True)
    yield channel
    conn.close()

@pytest.fixture
def curso_ejemplo(sessions):
    db_gw, _, _ = sessions
    curso = Curso(
        nombre="Biología General",
        seccion="A",
        periodo="2026-1",
        docente="Prof. García",
        color="green",
    )
    db_gw.add(curso)
    db_gw.commit()
    db_gw.refresh(curso)
    return curso

@pytest.fixture
def solucionario_ejemplo(sessions, curso_ejemplo):
    db_gw, _, _ = sessions
    sol = Solucionario(
        curso_id=curso_ejemplo.id,
        nombre="Examen Parcial Biología",
        respuestas={
            "1": "B", "2": "C", "3": "C", "4": "C",
            "5": "C", "6": "B", "7": "C", "8": "C",
            "9": "ES LA CAPACIDAD DEL ORGANISMO PARA MANTENER CONDICIONES INTERNAS ESTABLES",
        },
        puntaje_total=20.0,
        puntajes_individuales={
            "1": 2.0, "2": 2.0, "3": 2.0, "4": 2.0,
            "5": 2.0, "6": 2.0, "7": 2.0, "8": 2.0, "9": 4.0,
        },
    )
    db_gw.add(sol)
    db_gw.commit()
    db_gw.refresh(sol)
    return sol

@pytest.fixture
def examen_ejemplo(sessions, solucionario_ejemplo):
    _, db_cal, _ = sessions
    examen = Examen(
        alumno_id="20232230",
        alumno_nombre="Pedro Sanchez",
        solucionario_id=solucionario_ejemplo.id,
        curso_id=solucionario_ejemplo.curso_id,
        archivo_original="examen_test.pdf",
        estado=EstadoExamen.OCR_COMPLETADO,
    )
    db_cal.add(examen)
    db_cal.commit()
    db_cal.refresh(examen)
    return examen

class TestCurso:
    def test_crear_curso(self, sessions):
        db_gw, _, _ = sessions
        curso = Curso(nombre="Matemática I", seccion="B",
                      periodo="2026-1", color="blue")
        db_gw.add(curso)
        db_gw.commit()

        encontrado = db_gw.query(Curso).filter_by(nombre="Matemática I").first()
        assert encontrado is not None
        assert encontrado.seccion == "B"
        assert encontrado.activo is True

    def test_soft_delete_curso(self, sessions, curso_ejemplo):
        db_gw, _, _ = sessions
        curso_ejemplo.activo = False
        db_gw.commit()

        activos = db_gw.query(Curso).filter_by(activo=True).all()
        assert curso_ejemplo not in activos

    def test_curso_tiene_relacion_con_solucionarios(
        self, sessions, solucionario_ejemplo, curso_ejemplo
    ):
        db_gw, _, _ = sessions
        db_gw.refresh(curso_ejemplo)
        assert len(curso_ejemplo.solucionarios) == 1
        assert curso_ejemplo.solucionarios[0].nombre == "Examen Parcial Biología"

class TestSolucionario:
    def test_crear_solucionario_con_puntajes_individuales(
        self, sessions, curso_ejemplo
    ):
        db_gw, _, _ = sessions
        sol = Solucionario(
            curso_id=curso_ejemplo.id,
            nombre="Test Sol",
            respuestas={"1": "A", "2": "B"},
            puntaje_total=10.0,
            puntajes_individuales={"1": 5.0, "2": 5.0},
        )
        db_gw.add(sol)
        db_gw.commit()
        db_gw.refresh(sol)

        assert sol.puntajes_individuales["1"] == 5.0
        assert sol.puntajes_individuales["2"] == 5.0

    def test_validar_suma_puntajes(self, sessions, curso_ejemplo):
        db_gw, _, _ = sessions
        puntajes = {"1": 2.0, "2": 2.0, "3": 2.0, "4": 2.0,
                    "5": 2.0, "6": 2.0, "7": 2.0, "8": 2.0, "9": 4.0}
        suma = sum(puntajes.values())
        assert suma == 20.0

    def test_num_preguntas_calculado(self, sessions, solucionario_ejemplo):
        assert len(solucionario_ejemplo.respuestas) == 9

class TestNormalizacion:
    def test_normalizar_mayusculas(self):
        assert normalizar("  a  ") == "A"

    def test_normalizar_elimina_puntuacion(self):
        assert normalizar("B.") == "B"
        assert normalizar("C,") == "C"

    def test_normalizar_vacio(self):
        assert normalizar("") == ""
        assert normalizar(None) == ""

class TestEquivalencia:
    def test_alternativa_correcta(self):
        assert son_equivalentes("B", "B") is True

    def test_alternativa_incorrecta(self):
        assert son_equivalentes("A", "B") is False

    def test_case_insensitive(self):
        assert son_equivalentes("b", "B") is True

    def test_texto_libre_70_pct_palabras(self):
        resp_alumno  = "La homeostasis es la capacidad del organismo para mantener equilibrio"
        resp_correcta = "ES LA CAPACIDAD DEL ORGANISMO PARA MANTENER CONDICIONES INTERNAS ESTABLES"
        resultado = son_equivalentes(resp_alumno, resp_correcta)
        assert isinstance(resultado, bool)

    def test_texto_vacio(self):
        assert son_equivalentes("", "B") is False
        assert son_equivalentes("B", "") is False

class TestCalculoNota:
    def _sol_data_uniforme(self):
        return {
            "respuestas": {str(i): "A" for i in range(1, 11)},
            "puntaje_total": 20.0,
            "puntaje_por_pregunta": 2.0,
            "puntajes_individuales": None,
        }

    def _sol_data_individual(self):
        return {
            "respuestas": {str(i): "A" for i in range(1, 10)},
            "puntaje_total": 20.0,
            "puntaje_por_pregunta": None,
            "puntajes_individuales": {
                "1": 2.0, "2": 2.0, "3": 2.0, "4": 2.0,
                "5": 2.0, "6": 2.0, "7": 2.0, "8": 2.0, "9": 4.0,
            },
        }

    def test_nota_maxima_puntaje_uniforme(self):
        sol = self._sol_data_uniforme()
        respuestas = [
            {"numero_pregunta": str(i), "es_correcta": True,
             "estado": "procesada"}
            for i in range(1, 11)
        ]
        nota, pct = calcular_nota(respuestas, sol)
        assert nota == 20.0
        assert pct == 100.0

    def test_nota_cero_puntaje_uniforme(self):
        sol = self._sol_data_uniforme()
        respuestas = [
            {"numero_pregunta": str(i), "es_correcta": False,
             "estado": "procesada"}
            for i in range(1, 11)
        ]
        nota, pct = calcular_nota(respuestas, sol)
        assert nota == 0.0
        assert pct == 0.0

    def test_nota_parcial_puntaje_uniforme(self):
        sol = self._sol_data_uniforme()
        respuestas = [
            {"numero_pregunta": str(i), "es_correcta": i <= 5,
             "estado": "procesada"}
            for i in range(1, 11)
        ]
        nota, pct = calcular_nota(respuestas, sol)
        assert nota == 10.0
        assert pct == 50.0

    def test_nota_puntajes_individuales_maximo(self):
        sol = self._sol_data_individual()
        respuestas = [
            {"numero_pregunta": str(i), "es_correcta": True,
             "estado": "procesada"}
            for i in range(1, 10)
        ]
        nota, pct = calcular_nota(respuestas, sol)
        assert nota == 20.0

    def test_nota_puntajes_individuales_parcial(self):
        sol = self._sol_data_individual()
        respuestas = [
            {"numero_pregunta": str(i),
             "es_correcta": i != 9,
             "estado": "procesada"}
            for i in range(1, 10)
        ]
        nota, _ = calcular_nota(respuestas, sol)
        assert nota == 16.0

    def test_nota_ignora_pendientes_revision(self):
        sol = self._sol_data_uniforme()
        respuestas = [
            {"numero_pregunta": "1", "es_correcta": True,  "estado": "procesada"},
            {"numero_pregunta": "2", "es_correcta": None,  "estado": "pendiente_revision"},
            {"numero_pregunta": "3", "es_correcta": False, "estado": "procesada"},
        ] + [
            {"numero_pregunta": str(i), "es_correcta": False, "estado": "procesada"}
            for i in range(4, 11)
        ]
        nota, _ = calcular_nota(respuestas, sol)
        assert nota == 2.0

    def test_sin_preguntas_devuelve_cero(self):
        sol = {"respuestas": {}, "puntaje_total": 20.0,
               "puntajes_individuales": None, "puntaje_por_pregunta": None}
        nota, pct = calcular_nota([], sol)
        assert nota == 0.0
        assert pct == 0.0

class TestProcesarResultadosOCR:
    def test_examen_calificado_correctamente(
        self, sessions, examen_ejemplo, solucionario_ejemplo
    ):
        _, db_cal, _ = sessions
        sol = solucionario_ejemplo

        mensaje = {
            "examen_id": examen_ejemplo.id,
            "alumno_id": examen_ejemplo.alumno_id,
            "solucionario_id": sol.id,
            "solucionario_data": {
                "respuestas": sol.respuestas,
                "puntaje_total": sol.puntaje_total,
                "puntaje_por_pregunta": sol.puntaje_por_pregunta,
                "puntajes_individuales": sol.puntajes_individuales,
            },
            "resultados_ocr": [
                {"numero_pregunta": "1", "texto_extraido": "B", "confianza": 0.92},
                {"numero_pregunta": "2", "texto_extraido": "C", "confianza": 0.89},
                {"numero_pregunta": "3", "texto_extraido": "C", "confianza": 0.91},
                {"numero_pregunta": "4", "texto_extraido": "C", "confianza": 0.87},
                {"numero_pregunta": "5", "texto_extraido": "C", "confianza": 0.93},
                {"numero_pregunta": "6", "texto_extraido": "B", "confianza": 0.88},
                {"numero_pregunta": "7", "texto_extraido": "C", "confianza": 0.90},
                {"numero_pregunta": "8", "texto_extraido": "C", "confianza": 0.85},
                {"numero_pregunta": "9",
                 "texto_extraido": "Capacidad del organismo para mantener equilibrio interno",
                 "confianza": 0.30},
            ],
        }

        procesar_resultados_ocr(mensaje, db_cal)
        db_cal.refresh(examen_ejemplo)

        assert examen_ejemplo.nota_final == 16.0
        assert examen_ejemplo.estado == EstadoExamen.PENDIENTE_REVISION

        respuestas = db_cal.query(RespuestaAlumno).filter_by(
            examen_id=examen_ejemplo.id).all()
        pendientes = [r for r in respuestas
                      if r.estado == EstadoRespuesta.PENDIENTE_REVISION]
        assert len(pendientes) == 1
        assert pendientes[0].numero_pregunta == 9

    def test_todas_correctas_aprobado(
        self, sessions, solucionario_ejemplo
    ):
        _, db_cal, _ = sessions
        examen = Examen(
            alumno_id="99999999",
            solucionario_id=solucionario_ejemplo.id,
            curso_id=solucionario_ejemplo.curso_id,
            estado=EstadoExamen.OCR_COMPLETADO,
        )
        db_cal.add(examen)
        db_cal.commit()
        db_cal.refresh(examen)

        sol = solucionario_ejemplo
        resultados_ocr = [
            {"numero_pregunta": "1", "texto_extraido": "B", "confianza": 0.95},
            {"numero_pregunta": "2", "texto_extraido": "C", "confianza": 0.94},
            {"numero_pregunta": "3", "texto_extraido": "C", "confianza": 0.96},
            {"numero_pregunta": "4", "texto_extraido": "C", "confianza": 0.91},
            {"numero_pregunta": "5", "texto_extraido": "C", "confianza": 0.88},
            {"numero_pregunta": "6", "texto_extraido": "B", "confianza": 0.92},
            {"numero_pregunta": "7", "texto_extraido": "C", "confianza": 0.90},
            {"numero_pregunta": "8", "texto_extraido": "C", "confianza": 0.93},
            {"numero_pregunta": "9",
             "texto_extraido": "ES LA CAPACIDAD DEL ORGANISMO PARA MANTENER CONDICIONES INTERNAS ESTABLES",
             "confianza": 0.85},
        ]

        procesar_resultados_ocr({
            "examen_id": examen.id,
            "alumno_id": examen.alumno_id,
            "solucionario_id": sol.id,
            "solucionario_data": {
                "respuestas": sol.respuestas,
                "puntaje_total": sol.puntaje_total,
                "puntaje_por_pregunta": sol.puntaje_por_pregunta,
                "puntajes_individuales": sol.puntajes_individuales,
            },
            "resultados_ocr": resultados_ocr,
        }, db_cal)

        db_cal.refresh(examen)
        assert examen.nota_final == 20.0
        assert examen.estado == EstadoExamen.CALIFICADO
        assert examen.porcentaje_aciertos == 100.0

    def test_examen_no_encontrado_no_lanza_excepcion(self, sessions):
        _, db_cal, _ = sessions
        mensaje = {
            "examen_id": 99999,
            "alumno_id": "00000",
            "solucionario_id": 1,
            "solucionario_data": {"respuestas": {}, "puntaje_total": 20.0,
                                  "puntajes_individuales": None,
                                  "puntaje_por_pregunta": 2.0},
            "resultados_ocr": [],
        }
        procesar_resultados_ocr(mensaje, db_cal)

class TestGeneracionReporte:
    def _crear_examen_calificado(self, db_cal, solucionario_id,
                                 alumno_id, nota, porcentaje, curso_id=1):
        examen = Examen(
            alumno_id=alumno_id,
            alumno_nombre=f"Alumno {alumno_id}",
            solucionario_id=solucionario_id,
            curso_id=curso_id,
            estado=EstadoExamen.CALIFICADO,
            nota_final=nota,
            porcentaje_aciertos=porcentaje,
        )
        db_cal.add(examen)
        db_cal.commit()
        db_cal.refresh(examen)
        return examen

    def test_reporte_con_examenes_aprobados_y_desaprobados(
        self, sessions, solucionario_ejemplo
    ):
        _, db_cal, _ = sessions
        sol_id   = solucionario_ejemplo.id
        curso_id = solucionario_ejemplo.curso_id

        self._crear_examen_calificado(db_cal, sol_id, "A001", 18.0, 90.0, curso_id)
        self._crear_examen_calificado(db_cal, sol_id, "A002", 14.0, 70.0, curso_id)
        self._crear_examen_calificado(db_cal, sol_id, "A003", 8.0,  40.0, curso_id)

        reporte = generar_reporte(
            solucionario_id=sol_id,
            curso_id=curso_id,
            nombre_reporte="Test Reporte",
            solicitud_id="test-001",
            db_cal=db_cal,
        )

        resumen = reporte["resumen"]
        assert resumen["total_examenes"] >= 3
        assert resumen["aprobados"] >= 2
        assert resumen["desaprobados"] >= 1
        assert resumen["nota_minima"] <= 8.0
        assert resumen["nota_maxima"] >= 18.0

    def test_reporte_vacio_cuando_no_hay_examenes(
        self, sessions, solucionario_ejemplo
    ):
        _, db_cal, _ = sessions
        reporte = generar_reporte(
            solucionario_id=9999,
            curso_id=9999,
            nombre_reporte="Vacío",
            solicitud_id="test-vacio",
            db_cal=db_cal,
        )
        assert reporte["resumen"]["total_examenes"] == 0
        assert reporte["resumen"]["promedio_notas"] is None

    def test_reporte_contiene_estructura_completa(
        self, sessions, solucionario_ejemplo
    ):
        _, db_cal, _ = sessions
        sol_id   = solucionario_ejemplo.id
        curso_id = solucionario_ejemplo.curso_id
        self._crear_examen_calificado(db_cal, sol_id, "B001", 16.0, 80.0, curso_id)

        reporte = generar_reporte(
            solucionario_id=sol_id,
            curso_id=curso_id,
            nombre_reporte="Estructura",
            solicitud_id="test-est",
            db_cal=db_cal,
        )

        assert "metadata" in reporte
        assert "resumen" in reporte
        assert "estadisticas_preguntas" in reporte
        assert "detalle_alumnos" in reporte
        assert reporte["metadata"]["nombre_reporte"] == "Estructura"

class TestRabbitMQ:
    def test_publicar_y_consumir_mensaje(self, rmq_channel):
        mensaje_enviado = {
            "examen_id": 42,
            "alumno_id": "12345",
            "solucionario_id": 1,
            "test": True,
        }
        rmq_channel.basic_publish(
            exchange="",
            routing_key="cola_calificacion",
            body=json.dumps(mensaje_enviado),
            properties=pika.BasicProperties(delivery_mode=2),
        )

        method, _, body = rmq_channel.basic_get("cola_calificacion", auto_ack=True)
        assert method is not None

        mensaje_recibido = json.loads(body)
        assert mensaje_recibido["examen_id"] == 42
        assert mensaje_recibido["alumno_id"] == "12345"

    def test_mensaje_json_invalido_no_bloquea_cola(self, rmq_channel):
        rmq_channel.basic_publish(
            exchange="",
            routing_key="cola_calificacion",
            body=b"esto no es json {{{",
            properties=pika.BasicProperties(delivery_mode=2),
        )
        rmq_channel.basic_publish(
            exchange="",
            routing_key="cola_calificacion",
            body=json.dumps({"examen_id": 99}).encode(),
            properties=pika.BasicProperties(delivery_mode=2),
        )

        m1, _, b1 = rmq_channel.basic_get("cola_calificacion", auto_ack=True)
        m2, _, b2 = rmq_channel.basic_get("cola_calificacion", auto_ack=True)

        assert m2 is not None
        assert json.loads(b2)["examen_id"] == 99

    def test_cola_es_durable(self, rmq_channel):
        rmq_channel.queue_declare(queue="cola_calificacion", durable=True)
        rmq_channel.queue_declare(queue="cola_reporte", durable=True)

class TestIntegridadBD:
    def test_examen_referencia_logica_solucionario(self, sessions):
        _, db_cal, _ = sessions
        examen = Examen(
            alumno_id="TEST001",
            solucionario_id=9999,
            estado=EstadoExamen.RECIBIDO,
        )
        db_cal.add(examen)
        db_cal.commit()
        assert examen.id is not None

    def test_respuesta_cascade_delete(self, sessions, examen_ejemplo):
        _, db_cal, _ = sessions
        r = RespuestaAlumno(
            examen_id=examen_ejemplo.id,
            numero_pregunta=1,
            respuesta_ocr="B",
            confianza_ocr=0.90,
            respuesta_correcta="B",
            es_correcta=True,
            estado=EstadoRespuesta.PROCESADA,
        )
        db_cal.add(r)
        db_cal.commit()

        db_cal.delete(examen_ejemplo)
        db_cal.commit()

        respuestas_huerfanas = db_cal.query(RespuestaAlumno).filter_by(
            examen_id=examen_ejemplo.id).all()
        assert len(respuestas_huerfanas) == 0

    def test_postgres_conexion_real(self, engines):
        engine_gw, engine_cal, engine_rep = engines
        for engine in (engine_gw, engine_cal, engine_rep):
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()")).fetchone()
                assert "PostgreSQL" in result[0]

    def test_tablas_creadas_en_las_3_bds(self, engines):
        engine_gw, engine_cal, engine_rep = engines

        with engine_gw.connect() as conn:
            tablas_gw = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            ).fetchall()
            nombres_gw = {r[0] for r in tablas_gw}
            assert "cursos" in nombres_gw
            assert "solucionarios" in nombres_gw

        with engine_cal.connect() as conn:
            tablas_cal = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            ).fetchall()
            nombres_cal = {r[0] for r in tablas_cal}
            assert "examenes" in nombres_cal
            assert "respuestas_alumno" in nombres_cal

        with engine_rep.connect() as conn:
            tablas_rep = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            ).fetchall()
            nombres_rep = {r[0] for r in tablas_rep}
            assert "reportes" in nombres_rep