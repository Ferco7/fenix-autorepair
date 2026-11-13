"""Receptor FastAPI: autenticación, validación y aceptación durable por SQS."""
import os  # Recupera el secreto sin incluirlo en el repositorio.
import json  # Decodifica después de verificar los bytes.
from fastapi import FastAPI, Request, HTTPException  # Interfaz HTTP del curso.
from starlette.concurrency import run_in_threadpool  # Evita bloquear el event loop.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.utils.crypto import verify
from fenix.utils.errors import ValidationError
from fenix.utils.state import load
from fenix.services.events import validate
from fenix.services.sqs import queue_url, publish

app = FastAPI(title="Fénix receptor de alertas")  # Un servidor, un worker Uvicorn.
MAX_BODY_BYTES = 16 * 1024  # Límite que también aplica si Content-Length miente.
INVENTORY_PATH = "data/inventory.json"  # Inventario durable creado por setup-demo.


async def _read_limited_body(request: Request) -> bytes:
    """Lee el cuerpo original sin conservar más de 16 KiB en memoria.

    Content-Length permite rechazar pronto; el conteo durante stream cubre
    transferencias chunked y cabeceras falsas. El proxy de producción debe
    aplicar el mismo límite antes de que Uvicorn reciba la solicitud.
    """
    length = request.headers.get("content-length")
    if length is not None and length.isdecimal() and int(length) > MAX_BODY_BYTES:
        raise HTTPException(413, "Cuerpo demasiado grande")

    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "Cuerpo demasiado grande")
        chunks.extend(chunk)
    return bytes(chunks)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """Construye objetos JSON sin aceptar dos veces la misma clave."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clave JSON duplicada")
        result[key] = value
    return result


def _reject_nonstandard_constant(_: str) -> None:
    """Rechaza NaN e Infinity, que no forman parte de JSON interoperable."""
    raise ValueError("Constante JSON no permitida")


def _publish_validated(event: dict) -> str:
    """Hace la publicación Boto3 síncrona fuera del event loop.

    ``run_in_threadpool`` espera esta función antes de responder 202. Por eso
    el endpoint no promete aceptación hasta recibir el MessageId de SQS.
    """
    url = queue_url(os.environ["QUEUE_PREFIX"])
    return publish(url, event)

@app.post("/webhook", status_code=202)
async def webhook(request: Request) -> dict:
    """Recibe un evento firmado y contesta 202 solo después de encolarlo.

    Args:
        request: Petición con X-Webhook-Signature y cuerpo de hasta 16 KiB.
    Returns:
        JSON con status=accepted, event_id y message_id de SQS.
    Raises:
        HTTPException: 401 firma; 400 JSON; 413 tamaño; 422 contrato; 503 SQS.
    Side Effects:
        Publica en SQS; no repara recursos ni llama a Telegram/Slack aquí.
    Notes:
        Leer bytes completos basta para el laboratorio; un proxy limitaría antes
        el tamaño de la transferencia en un despliegue real.
    """
    raw = await _read_limited_body(request)  # Conserva exactamente los bytes firmados.
    signatures = request.headers.getlist("x-webhook-signature")
    header = signatures[0] if len(signatures) == 1 else ""
    try:
        verify(os.environ.get("WEBHOOK_SECRET", ""), header, raw)
    except ValidationError:
        # No se diferencia formato, reloj o digest: evita revelar pistas del HMAC.
        raise HTTPException(401, "Firma de webhook inválida") from None

    try:
        text = raw.decode("utf-8")  # json.loads(bytes aceptaría UTF-16; no aquí.
        event = json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                           parse_constant=_reject_nonstandard_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise HTTPException(400, "JSON inválido") from None

    try:
        inventory = await run_in_threadpool(load, INVENTORY_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(503, "Inventario no disponible") from None
    if not isinstance(inventory, dict):
        raise HTTPException(503, "Inventario no disponible")
    try:
        event = validate(event, inventory)
    except ValidationError:
        raise HTTPException(422, "Evento no válido") from None

    try:
        # Boto3 es síncrono. Se delega a un hilo y se espera su confirmación.
        message_id = await run_in_threadpool(_publish_validated, event)
    except (BotoCoreError, ClientError, OSError, KeyError, ValueError, ValidationError):
        raise HTTPException(503, "Cola no disponible") from None
    return {"status": "accepted", "event_id": event["event_id"],
            "message_id": message_id}
