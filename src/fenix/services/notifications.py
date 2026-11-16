"""Adaptador HTTP guiado. Elegir Telegram O Slack, no ambos obligatoriamente."""
import os  # Recupera credenciales fuera del repositorio.
import time  # Acota la espera pedida por el proveedor.
import requests  # Aplica timeout explícito a cada llamada HTTP.
from fenix.utils.errors import PermanentError, RetryableError

TIMEOUT = (2, 5)  # (conexión, lectura) en segundos; nunca espera indefinida.
MAX_TEXT = 1000  # Límite público del resumen enviado.
MAX_DELAY = 30  # Tope de espera ante Retry-After, en segundos.


def _text(text: str) -> str:
    """Recorta el resumen al límite público antes de enviarlo.

    Args:
        text: Resumen construido por el llamador.
    Returns:
        Los primeros 1000 caracteres, sin secretos ni raw body.
    """
    return text[:MAX_TEXT]


def _check(response: requests.Response) -> None:
    """Clasifica la respuesta HTTP antes de interpretar su cuerpo.

    Args:
        response: Respuesta ya recibida del proveedor.
    Returns:
        None solo si el status es 200.
    Raises:
        RetryableError: 429 o 5xx, con demora acotada ante Retry-After.
        PermanentError: Cualquier otro status distinto de 200.
    """
    if response.status_code == 429:  # Límite temporal del proveedor.
        raw = response.headers.get("Retry-After", "0")
        try:
            delay = float(raw)
        except (TypeError, ValueError):
            delay = 0.0  # Encabezado ausente o inválido: no se espera.
        if delay > 0:
            time.sleep(min(delay, MAX_DELAY))  # Nunca bloquea más de 30 segundos.
        raise RetryableError("El proveedor limitó el envío (429); reintentar")
    if response.status_code >= 500:  # Fallo temporal del lado del proveedor.
        raise RetryableError(f"El proveedor no está disponible ({response.status_code})")
    if response.status_code != 200:  # Credenciales o payload rechazados.
        raise PermanentError(f"El proveedor rechazó el aviso ({response.status_code})")


def _telegram(text: str) -> None:
    """Publica en el chat configurado y exige confirmación funcional.

    Args:
        text: Resumen público ya recortado.
    Raises:
        PermanentError: Credenciales ausentes, JSON ilegible u ok distinto de True.
        RetryableError: Timeout, conexión, 429 o 5xx.
    Notes:
        Un HTTP 200 con ok=false es un rechazo funcional, no un éxito.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise PermanentError("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=TIMEOUT,
        )
    except (requests.Timeout, requests.ConnectionError):
        raise RetryableError("No se pudo contactar a Telegram") from None

    _check(response)  # 429 y 5xx se resuelven antes de leer el cuerpo.

    try:
        payload = response.json()
    except ValueError:
        raise PermanentError("Telegram devolvió una respuesta ilegible") from None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise PermanentError("Telegram rechazó el mensaje")


def _slack(text: str) -> None:
    """Publica en el webhook configurado y exige el cuerpo "ok".

    Args:
        text: Resumen público ya recortado.
    Raises:
        PermanentError: URL ausente o cuerpo distinto de "ok".
        RetryableError: Timeout, conexión, 429 o 5xx.
    """
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        raise PermanentError("Falta SLACK_WEBHOOK_URL")

    try:
        response = requests.post(url, json={"text": text}, timeout=TIMEOUT)
    except (requests.Timeout, requests.ConnectionError):
        raise RetryableError("No se pudo contactar a Slack") from None

    _check(response)
    if response.text.strip() != "ok":  # Slack responde texto plano, no JSON.
        raise PermanentError("Slack rechazó el mensaje")


def notify(text: str) -> None:
    """Envía un mensaje breve y valida la respuesta del proveedor seleccionado.

    Args:
        text: Resumen público de hasta 1000 caracteres, sin secretos ni raw body.
    Returns:
        None únicamente después de confirmar éxito del proveedor.
    Raises:
        RetryableError: Timeout, conexión, 429 o respuesta 5xx.
        PermanentError: Configuración inválida, 4xx definitivo o rechazo funcional.
    Side Effects:
        Publica en el chat/canal del grupo. Un timeout puede causar duplicados.
    Notes:
        El modo console sirve para desarrollo; no reemplaza la evidencia final real.
        No registrar la excepción requests original: puede contener el token en URL.
    """
    mode = os.getenv("NOTIFY_PROVIDER", "console").strip().lower()
    message = _text(text)

    if mode == "console":  # Ensayo local sin credenciales de terceros.
        print(message)  # No imprimir eventos completos o URLs privadas.
        return

    providers = {"telegram": _telegram, "slack": _slack}
    provider = providers.get(mode)
    if provider is None:
        raise PermanentError(f"NOTIFY_PROVIDER no soportado: {mode}")
    provider(message)