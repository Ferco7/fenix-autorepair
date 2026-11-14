"""Firma de apoyo y verificación a completar por el integrante 3."""
import hashlib  # Selecciona SHA-256 para autenticar el contenido.
import hmac  # Usa una comparación segura para las firmas.
import time  # Comprueba la ventana temporal.
from fenix.utils.errors import ValidationError  # Rechazo de autenticación público.


def signature(secret: str, timestamp: int, body: bytes) -> str:
    """Firma exactamente timestamp, punto y cuerpo binario original.

    Args:
        secret: Secreto compartido de al menos 16 caracteres, leído del entorno.
        timestamp: Unix epoch en segundos, igual al enviado en la cabecera.
        body: Bytes exactos enviados por HTTP; no volver a serializar el JSON.
    Returns:
        HMAC-SHA256 hexadecimal de 64 caracteres.
    Raises:
        ValidationError: Si el secreto es demasiado corto.
    """
    if len(secret) < 16:  # Se comprueba también al enviar la prueba.
        raise ValidationError("Configurar WEBHOOK_SECRET de 16 caracteres o más")
    signed = str(timestamp).encode("ascii") + b"." + body  # Prefijo autenticado.
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify(secret: str, header: str, body: bytes, now: int | None = None) -> None:
    """Rechaza cabeceras ambiguas y firmas o fechas inválidas.

    Args:
        secret: Secreto compartido del entorno, nunca del payload.
        header: Cabecera exacta t=<epoch>,v1=<hex> sin claves duplicadas.
        body: Bytes del cuerpo antes de llamar a json.loads.
        now: Reloj inyectable para pruebas; None usa time.time.
    Returns:
        None si las comprobaciones son satisfactorias.
    Raises:
        ValidationError: Formato inválido, firma incorrecta o diferencia mayor a 300 s.
    Notes:
        La ventana de tiempo mitiga replay antiguo. No impide repetir un evento
        válido dentro de la ventana; event_id e idempotencia cubren ese caso.
    """
    invalid = ValidationError("Firma de webhook inválida")
    if not isinstance(header, str) or not isinstance(body, bytes):
        raise invalid

    # Se exige exactamente el formato del contrato: dos partes, sin claves
    # repetidas ni parámetros que un intermediario pueda interpretar distinto.
    parts = header.split(",")
    if len(parts) != 2:
        raise invalid
    values: dict[str, str] = {}
    for part in parts:
        key, separator, value = part.partition("=")
        if (separator != "=" or not key or not value or key in values
                or key not in {"t", "v1"}):
            raise invalid
        values[key] = value
    if set(values) != {"t", "v1"}:
        raise invalid

    timestamp_text = values["t"]
    supplied = values["v1"]
    if (not timestamp_text.isascii() or not timestamp_text.isdecimal()
            or len(supplied) != 64
            or any(char not in "0123456789abcdef" for char in supplied)):
        raise invalid

    try:
        timestamp = int(timestamp_text)
        current = int(time.time()) if now is None else int(now)
    except (TypeError, ValueError, OverflowError):
        raise invalid from None
    if abs(current - timestamp) > 300:
        raise invalid

    try:
        expected = signature(secret, timestamp, body)
    except (TypeError, ValidationError):
        # Una configuración ausente también falla cerrada y no expone su detalle.
        raise invalid from None
    if not hmac.compare_digest(expected, supplied):
        raise invalid
