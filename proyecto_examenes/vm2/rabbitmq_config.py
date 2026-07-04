import pika
import json
import logging
import os
import time
from typing import Callable

logger = logging.getLogger(__name__)

QUEUE_PREPROCESAMIENTO = "cola_preprocesamiento"
QUEUE_OCR              = "cola_ocr"
QUEUE_CALIFICACION     = "cola_calificacion"
QUEUE_REPORTE          = "cola_reporte"

def get_rabbitmq_params() -> pika.ConnectionParameters:
    credentials = pika.PlainCredentials(
        username=os.getenv("RABBITMQ_USER", "admin"),
        password=os.getenv("RABBITMQ_PASSWORD", "admin123"),
    )
    return pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "192.168.18.97"),
        port=int(os.getenv("RABBITMQ_PORT", 5672)),
        virtual_host=os.getenv("RABBITMQ_VHOST", "/"),
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

def connect_with_retry(max_retries: int = 15, delay: int = 5) -> pika.BlockingConnection:
    params = get_rabbitmq_params()
    for attempt in range(1, max_retries + 1):
        try:
            connection = pika.BlockingConnection(params)
            logger.info(f"Conectado a RabbitMQ en {params.host}:{params.port}")
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            logger.warning(
                f"Intento {attempt}/{max_retries} — No se pudo conectar a "
                f"RabbitMQ ({params.host}): {e}. Reintentando en {delay}s..."
            )
            time.sleep(delay)
    raise RuntimeError(
        f"No se pudo conectar a RabbitMQ en {params.host} tras {max_retries} intentos."
    )

def declare_queues(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    queues = [QUEUE_PREPROCESAMIENTO, QUEUE_OCR, QUEUE_CALIFICACION, QUEUE_REPORTE]
    for queue in queues:
        channel.queue_declare(queue=queue, durable=True)

def publish_message(channel: pika.adapters.blocking_connection.BlockingChannel,
                    queue: str,
                    message: dict) -> None:
    body = json.dumps(message, ensure_ascii=False)
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=body,
        properties=pika