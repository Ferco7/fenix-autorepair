"""Contratos de validación a completar por el integrante 1."""
import re # Comprueba el formato de los identificadores.
from datetime import datetime # Interpreta fechas ISO 8601.
from fenix.utils.errors import ValidationError # Error público del dominio.


def identifier(value: str) -> str:
    """Valida un identificador corto y devuelve su texto sin modificar."""
    if not isinstance(value, str):
        raise ValidationError("El identificador debe ser texto")
    if re.fullmatch(r"[a-z0-9-]{3,32}", value) is None:
        raise ValidationError("El identificador no cumple el formato")
    return value


def ttl_seconds(value: str) -> int:
    """Valida el TTL didáctico: entero entre 60 y 600 segundos."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
        raise ValidationError("El TTL debe ser un número entero")
    ttl = int(value)
    if not 60 <= ttl <= 600:
        raise ValidationError("El TTL debe estar entre 60 y 600 segundos")
    return ttl


def utc_text(value: str) -> datetime:
    """Interpreta una fecha UTC explícita sin aceptar fechas ingenuas."""
    if not isinstance(value, str):
        raise ValidationError("La fecha debe ser texto")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError("La fecha no es ISO 8601 válida") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValidationError("La fecha debe incluir UTC explícito")
    return parsed

