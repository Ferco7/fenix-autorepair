"""Worker central: un mensaje por vez y ACK solo tras el éxito durable."""
import json  # Convierte Body solo dentro del control por mensaje.
import time  # Evita un bucle intensivo si el emulador no responde.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.services.sqs import receive, acknowledge, retry_later
from fenix.utils.errors import ProjectError


def run(url: str, handler, logger, once: bool = False) -> None:
    """Consume mensajes y confirma únicamente resultados durables.

    Args:
        url: URL de la cola de trabajo, obtenida por get_queue_url.
        handler: Callable handler(event) que revalida y ejecuta el negocio.
        logger: Logger JSON del proceso worker.
        once: Si es True, realiza una sola consulta y termina; útil para pruebas.
    Returns:
        None al terminar la consulta única o al detenerse mediante Ctrl+C.
    Raises:
        NotImplementedError: Si todavía falta una plantilla del equipo.
    Side Effects:
        Consume, reprograma o confirma mensajes; nunca confirma en finally.
    """
    while True:
        try:
            messages = receive(url)
        except (BotoCoreError, ClientError) as error:
            logger.error("fallo_transporte",
                         extra={"status": type(error).__name__})
            if once:
                return
            time.sleep(2)
            continue

        for message in messages:
            message_id = message.get("MessageId")  # Contexto antes de parsear.
            try:
                event = json.loads(message.get("Body", ""))
                if not isinstance(event, dict):
                    raise ValueError("El cuerpo del mensaje no es un objeto JSON")
                handler(event)
            except NotImplementedError:
                raise  # Una plantilla pendiente debe verse, nunca confirmarse.
            except (ValueError, TypeError, KeyError, ProjectError,
                    BotoCoreError, ClientError, OSError) as error:
                logger.error("mensaje_reintentable",
                             extra={"message_id": message_id,
                                    "status": type(error).__name__})
                try:
                    retry_later(url, message)
                except (BotoCoreError, ClientError, KeyError) as retry_error:
                    logger.error("fallo_retry",
                                 extra={"message_id": message_id,
                                        "status": type(retry_error).__name__})
                    if once:
                        return
                    time.sleep(2)
                continue

            try:
                acknowledge(url, message["ReceiptHandle"])
            except (BotoCoreError, ClientError, KeyError) as error:
                logger.error("fallo_ack",
                             extra={"message_id": message_id,
                                    "status": type(error).__name__})
                if once:
                    return
                time.sleep(2)
            else:
                logger.info("mensaje_confirmado",
                            extra={"message_id": message_id, "status": "ok"})

        if once:
            return