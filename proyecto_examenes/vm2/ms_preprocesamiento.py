import base64
import json
import logging
import os
import signal
import sys
import shutil
from pathlib import Path
from typing import List

import pika
import pdf2image

from rabbitmq_config import (
    connect_with_retry, declare_queues, publish_message,
    start_consumer, QUEUE_PREPROCESAMIENTO, QUEUE_OCR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ms_preprocesamiento")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/examenes_uploads")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/tmp/examenes_procesados")
PDF_DPI = int(os.getenv("PDF_DPI", "300"))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)


def pdf_a_imagenes(ruta_pdf: str, examen_id: int) -> List[str]:
    logger.info(f"Convirtiendo PDF: {ruta_pdf}")
    rutas = pdf2image.convert_from_path(
        ruta_pdf,
        dpi=PDF_DPI,
        fmt="PNG",
        output_folder=PROCESSED_DIR,
        output_file=f"examen_{examen_id}_pag",
        paths_only=True,
    )
    logger.info(f"PDF convertido: {len(rutas)} página(s)")
    return rutas


def preparar_imagen(ruta_original: str, examen_id: int) -> str:
    nombre = f"examen_{examen_id}{Path(ruta_original).suffix}"
    ruta_dst = os.path.join(PROCESSED_DIR, nombre)
    shutil.copy2(ruta_original, ruta_dst)
    logger.info(f"Imagen copiada: {ruta_dst}")
    return ruta_dst


def callback_preprocesamiento(
        ch: pika.adapters.blocking_connection.BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
) -> None:
    pub_conn = None
    try:
        msg = json.loads(body.decode("utf-8"))
        examen_id = msg.get("examen_id")
        alumno_id = msg.get("alumno_id")
        tipo_archivo = msg.get("tipo_archivo", "").lower()
        nombre_archivo = msg.get("nombre_archivo", f"{examen_id}.jpg")
        contenido_b64 = msg.get("contenido_base64")

        logger.info(
            f"Preprocesando examen_id={examen_id} "
            f"alumno={alumno_id} tipo={tipo_archivo}"
        )

        if not contenido_b64:
            raise ValueError(f"Sin contenido_base64 para examen_id={examen_id}")

        contenido_bytes = base64.b64decode(contenido_b64)
        ruta_archivo = os.path.join(UPLOAD_DIR, nombre_archivo)
        with open(ruta_archivo, "wb") as f:
            f.write(contenido_bytes)
        logger.info(f"Archivo reconstruido: {ruta_archivo}")

        if tipo_archivo == "pdf":
            imagenes = pdf_a_imagenes(ruta_archivo, examen_id)
        else:
            imagenes = [preparar_imagen(ruta_archivo, examen_id)]

        pub_conn = connect_with_retry()
        pub_channel = pub_conn.channel()
        declare_queues(pub_channel)

        publish_message(pub_channel, QUEUE_OCR, {
            "examen_id": examen_id,
            "alumno_id": alumno_id,
            "solucionario_id": msg.get("solucionario_id"),
            "solucionario_data": msg.get("solucionario_data", {}),
            "imagenes_procesadas": imagenes,
            "total_paginas": len(imagenes),
        })

        logger.info(f"Examen id={examen_id}: {len(imagenes)} imágenes enviadas.")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except (ValueError, FileNotFoundError) as e:
        logger.error(f"Error de datos: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.exception(f"Error inesperado: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    finally:
        if pub_conn and not pub_conn.is_closed:
            pub_conn.close()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    logger.info("Iniciando ms_preprocesamiento...")

    start_consumer(
        queue=QUEUE_PREPROCESAMIENTO,
        callback=callback_preprocesamiento,
        prefetch_count=2,
    )