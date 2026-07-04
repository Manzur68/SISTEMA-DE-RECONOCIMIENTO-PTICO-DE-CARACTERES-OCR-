import pika
import json
import logging
import os
import time
from typing import Callable, Optional

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
        host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        port=int(os.getenv("RABBITMQ_PORT", 5672)),
        virtual_host=os.getenv("RABBITMQ_VHOST", "/"),
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

def connect_with_retry(max_retries: int = 10, delay: int = 5) -> pika.BlockingConnection:
    params = get_rabbitmq_params()
    for attempt in range(1, max_retries + 1):
        try:
            connection = pika.BlockingConnection(params)
            logger.info("Conectado a RabbitMQ exitosamente.")
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            logger.warning(f"Intento {attempt}/{max_retries} fallido: {e}. Reintentando en {delay}s...")
            time.sleep(delay)
    raise RuntimeError("No se pudo conectar a RabbitMQ después de todos los intentos.")

def declare_queues(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    queues = [
        QUEUE_PREPROCESAMIENTO,
        QUEUE_OCR,
        QUEUE_CALIFICACION,
        QUEUE_REPORTE,
    ]
    for queue in queues:
        channel.queue_declare(queue=queue, durable=True)
        logger.debug(f"Cola declarada: {queue}")

def publish_message(channel: pika.adapters.blocking_connection.BlockingChannel,
                    queue: str,
                    message: dict) -> None:
    body = json.dumps(message, ensure_ascii=False)
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=body,
        properties=pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
        ),
    )
    logger.info(f"Mensaje publicado en '{queue}': {list(message.keys())}")

def start_consumer(queue: str,
                   callback: Callable,
                   prefetch_count: int = 1) -> None:
    while True:
        try:
            connection = connect_with_retry()
            channel = connection.channel()
            declare_queues(channel)
            channel.basic_qos(prefetch_count=prefetch_count)
            channel.basic_consume(queue=queue, on_message_callback=callback)
            logger.info(f"Escuchando cola '{queue}'...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Conexión perdida: {e}. Reconectando en 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Consumer detenido manualmente.")
            break