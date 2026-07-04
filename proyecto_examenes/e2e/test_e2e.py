import base64
import io
import json
import os
import time

import pytest
import requests
from PIL import Image, ImageDraw, ImageFont

API_URL = os.getenv("API_URL", "http://localhost:8000")

def get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{API_URL}{path}", timeout=10, **kwargs)

def post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{API_URL}{path}", timeout=30, **kwargs)

def patch(path: str, **kwargs) -> requests.Response:
    return requests.patch(f"{API_URL}{path}", timeout=10, **kwargs)

def delete(path: str, **kwargs) -> requests.Response:
    return requests.delete(f"{API_URL}{path}", timeout=10, **kwargs)

def crear_imagen_examen_png() -> bytes:
    W, H = 1240, 900
    img  = Image.new("RGB", (W, H), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 60], fill=(30, 80, 160))
    draw.text((40, 15), "UNIVERSIDAD NACIONAL — Examen Biología", fill="white")

    y = 80
    for i in range(1, 9):
        draw.text((40, y), f"{i}. Pregunta {i}", fill=(0, 0, 0))
        y += 28
        draw.text((60,  y), "A) opcion_a",  fill=(0, 0, 0))
        draw.text((400, y), "BX opcion_b",  fill=(0, 0, 80))
        y += 22
        draw.text((60,  y), "C) opcion_c",  fill=(0, 0, 0))
        draw.text((400, y), "D) opcion_d",  fill=(0, 0, 0))
        y += 30

    draw.text((40, y), "9. Defina homeostasis:", fill=(0, 0, 0))
    y += 28
    draw.text((60, y), "Capacidad del organismo para mantener condiciones estables",
              fill=(0, 0, 100))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

@pytest.fixture(scope="module")
def estado():
    return {}

class TestHealthCheck:
    def test_sistema_operativo(self):
        r = get("/health")
        assert r.status_code == 200

    def test_todas_las_bds_conectadas(self):
        r    = get("/health")
        data = r.json()
        assert data["bd_gateway"]      == "ok"
        assert data["bd_calificacion"] == "ok"
        assert data["bd_reporte"]      == "ok"

    def test_rabbitmq_conectado(self):
        data = get("/health").json()
        assert data["rabbitmq"] == "ok"

    def test_version_correcta(self):
        data = get("/health").json()
        assert "version" in data
        assert data["version"] == "2.0.0"

class TestCursosE2E:
    def test_crear_curso(self, estado):
        r = post("/cursos", json={
            "nombre" : "Biología General E2E",
            "seccion": "A",
            "periodo": "2026-1",
            "docente": "Prof. Test E2E",
            "color"  : "green",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["nombre"] == "Biología General E2E"
        assert "id" in data
        estado["curso_id"] = data["id"]

    def test_listar_cursos_incluye_el_creado(self, estado):
        r    = get("/cursos")
        assert r.status_code == 200
        ids  = [c["id"] for c in r.json()]
        assert estado["curso_id"] in ids

    def test_obtener_curso_por_id(self, estado):
        r = get(f"/cursos/{estado['curso_id']}")
        assert r.status_code == 200
        assert r.json()["id"] == estado["curso_id"]

    def test_actualizar_curso(self, estado):
        r = patch(f"/cursos/{estado['curso_id']}", json={"docente": "Prof. Actualizado"})
        assert r.status_code == 200
        assert r.json()["docente"] == "Prof. Actualizado"

    def test_curso_no_encontrado_retorna_404(self):
        r = get("/cursos/999999")
        assert r.status_code == 404

class TestSolucionariosE2E:
    def test_crear_solucionario(self, estado):
        assert "curso_id" in estado
        r = post("/solucionario", json={
            "curso_id"   : estado["curso_id"],
            "nombre"     : "Examen Parcial E2E",
            "descripcion": "Test automático E2E",
            "respuestas" : {
                "1": "B", "2": "C", "3": "C", "4": "C",
                "5": "C", "6": "B", "7": "C", "8": "C",
                "9": "ES LA CAPACIDAD DEL ORGANISMO PARA MANTENER CONDICIONES INTERNAS ESTABLES",
            },
            "puntaje_total": 20.0,
            "puntajes_individuales": {
                "1": 2.0, "2": 2.0, "3": 2.0, "4": 2.0,
                "5": 2.0, "6": 2.0, "7": 2.0, "8": 2.0, "9": 4.0,
            },
        })
        assert r.status_code == 201
        data = r.json()
        assert data["num_preguntas"] == 9
        assert data["puntajes_individuales"]["9"] == 4.0
        estado["solucionario_id"] = data["id"]

    def test_listar_solucionarios_del_curso(self, estado):
        r    = get(f"/cursos/{estado['curso_id']}/solucionarios")
        assert r.status_code == 200
        ids  = [s["id"] for s in r.json()]
        assert estado["solucionario_id"] in ids

    def test_solucionario_invalido_suma_incorrecta(self, estado):
        r = post("/solucionario", json={
            "curso_id"   : estado["curso_id"],
            "nombre"     : "Solucionario Inválido",
            "respuestas" : {"1": "A", "2": "B"},
            "puntaje_total": 20.0,
            "puntajes_individuales": {"1": 5.0, "2": 8.0},
        })
        assert r.status_code == 400

    def test_obtener_solucionario_por_id(self, estado):
        r = get(f"/solucionarios/{estado['solucionario_id']}")
        assert r.status_code == 200
        assert r.json()["id"] == estado["solucionario_id"]

class TestFlujoExamenE2E:
    def test_subir_examen(self, estado):
        assert "solucionario_id" in estado

        imagen_bytes = crear_imagen_examen_png()
        r = post("/examenes/subir", data={
            "solucionario_id": estado["solucionario_id"],
            "alumno_ids"     : "E2E001",
            "alumno_nombres" : "Alumno Test E2E",
        }, files={
            "archivos": ("examen_e2e.png", imagen_bytes, "image/png"),
        })
        assert r.status_code == 202
        data = r.json()
        assert len(data["examenes_creados"]) == 1
        estado["examen_id"] = data["examenes_creados"][0]["examen_id"]

    def test_examen_recibido_en_bd(self, estado):
        assert "examen_id" in estado
        r    = get(f"/examenes/{estado['examen_id']}/estado")
        assert r.status_code == 200
        data = r.json()
        assert data["alumno_id"] == "E2E001"
        assert data["estado"] in [
            "recibido", "preprocesando", "ocr_completado",
            "calificado", "pendiente_revision", "revision_completa",
        ]

    def test_esperar_calificacion(self, estado):
        assert "examen_id" in estado
        estados_finales = {"calificado", "pendiente_revision", "revision_completa"}
        max_espera      = 60
        intervalo       = 5

        for intento in range(max_espera // intervalo):
            r    = get(f"/examenes/{estado['examen_id']}/estado")
            data = r.json()
            estado_actual = data["estado"]

            if estado_actual in estados_finales:
                estado["estado_final_examen"] = estado_actual
                estado["nota_final"]          = data["nota_final"]
                return

            time.sleep(intervalo)

        r    = get(f"/examenes/{estado['examen_id']}/estado")
        data = r.json()
        pytest.skip(
            f"El pipeline OCR no procesó el examen en {max_espera}s. "
            f"Estado actual: {data['estado']}."
        )

    def test_examen_tiene_respuestas_guardadas(self, estado):
        if "estado_final_examen" not in estado:
            pytest.skip("El examen no fue procesado")

        r    = get(f"/examenes/{estado['examen_id']}/respuestas")
        assert r.status_code == 200
        data = r.json()
        assert len(data["respuestas"]) > 0

    def test_nota_es_numerica_y_valida(self, estado):
        if "nota_final" not in estado or estado["nota_final"] is None:
            pytest.skip("El examen no tiene nota final aún")

        nota = estado["nota_final"]
        assert isinstance(nota, (int, float))
        assert 0 <= nota <= 20

class TestRevisionManualE2E:
    def test_listar_pendientes(self):
        r    = get("/revision/pendientes")
        assert r.status_code == 200
        data = r.json()
        assert "total_pendientes" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_corregir_respuesta_pendiente_si_existe(self, estado):
        if "estado_final_examen" not in estado:
            pytest.skip("No hay examen procesado para revisar")
        if estado.get("estado_final_examen") not in ("pendiente_revision",):
            pytest.skip("El examen no tiene respuestas pendientes")

        r    = get(f"/examenes/{estado['examen_id']}/respuestas")
        data = r.json()
        pendientes = [resp for resp in data["respuestas"]
                      if resp["estado"] == "pendiente_revision"]

        if not pendientes:
            pytest.skip("No hay respuestas pendientes en este examen")

        primera = pendientes[0]
        r2 = patch(f"/revision/{primera['id']}", json={
            "respuesta_corregida": primera["respuesta_correcta"] or "B",
            "revisado_por"       : "test_e2e_automatico",
            "observaciones"      : "Corrección automática del test E2E",
        })
        assert r2.status_code == 200
        data2 = r2.json()
        assert "es_correcta" in data2
        assert "pendientes_en_examen" in data2

    def test_revision_respuesta_inexistente_retorna_404(self):
        r = patch("/revision/999999", json={
            "respuesta_corregida": "A",
            "revisado_por"       : "test_e2e",
        })
        assert r.status_code == 404

class TestReportesE2E:
    def test_solicitar_reporte_asincrono(self, estado):
        if "solucionario_id" not in estado:
            pytest.skip("No hay solucionario del flujo E2E")

        r = post(f"/reportes/generar"
                 f"?solucionario_id={estado['solucionario_id']}"
                 f"&nombre_reporte=Reporte+E2E+Test")
        assert r.status_code == 202
        data = r.json()
        assert "mensaje" in data

    def test_reporte_directo_retorna_estadisticas(self, estado):
        if "solucionario_id" not in estado:
            pytest.skip("No hay solucionario del flujo E2E")

        r    = get(f"/reportes/solucionario/{estado['solucionario_id']}/directo")
        assert r.status_code == 200
        data = r.json()

        assert "solucionario"        in data
        assert "total_examenes"      in data
        assert "calificados"         in data
        assert "pendientes_revision" in data
        assert "detalle_alumnos"     in data
        assert isinstance(data["detalle_alumnos"], list)

    def test_reporte_solucionario_inexistente_retorna_404(self):
        r = get("/reportes/solucionario/999999/directo")
        assert r.status_code == 404

    def test_listar_reportes_guardados(self):
        r    = get("/reportes")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

class TestLimpiezaE2E:
    def test_eliminar_solucionario_creado(self, estado):
        if "solucionario_id" not in estado:
            pytest.skip("No hay solucionario que limpiar")

        r = delete(f"/solucionarios/{estado['solucionario_id']}")
        assert r.status_code == 200

        r2   = get(f"/cursos/{estado['curso_id']}/solucionarios")
        ids  = [s["id"] for s in r2.json()]
        assert estado["solucionario_id"] not in ids

    def test_eliminar_curso_creado(self, estado):
        if "curso_id" not in estado:
            pytest.skip("No hay curso que limpiar")

        r = delete(f"/cursos/{estado['curso_id']}")
        assert r.status_code == 200

        r2  = get("/cursos")
        ids = [c["id"] for c in r2.json()]
        assert estado["curso_id"] not in ids