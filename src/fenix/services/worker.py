"""Plantilla central de integración: un worker, un mensaje por vez."""
import json  # Convierte Body solo dentro del control por mensaje.
import time  # Evita un bucle intensivo si el emulador no responde.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.services.sqs import receive, acknowledge, retry_later


def run(url: str, handler, logger, once: bool = False) -> None:
    """Consume mensajes y confirma únicamente resultados durables."""
    while True:
        try:
            messages = receive(url)
        except (BotoCoreError, ClientError) as error:
            logger.error("fallo_transporte", extra={"status": type(error).__name__})
            if once:
                return
            time.sleep(2)
            continue

        for message in messages:
            message_id = message.get("MessageId")
            receipt = message.get("ReceiptHandle")
            try:
                event = json.loads(message.get("Body", ""))
                if not isinstance(event, dict):
                    raise ValueError("El cuerpo del mensaje no es un objeto JSON")
                handler(event)
            except NotImplementedError:
                raise
            except Exception as error:  # JSON, validación, negocio o red.
                logger.error("mensaje_reintentable",
                             extra={"message_id": message_id,
                                    "status": type(error).__name__})
                try:
                    retry_later(url, message)
                except Exception as retry_error:
                    logger.error("fallo_retry",
                                 extra={"message_id": message_id,
                                        "status": type(retry_error).__name__})
                    if once:
                        return
                    time.sleep(2)
                continue

            try:
                acknowledge(url, receipt)
            except (BotoCoreError, ClientError) as error:
                logger.error("fallo_ack",
                             extra={"message_id": message_id,
                                    "status": type(error).__name__})
                if once:
                    return
                time.sleep(2)
            else:
                logger.info("mensaje_confirmado", extra={"message_id": message_id})

        if once:
            return