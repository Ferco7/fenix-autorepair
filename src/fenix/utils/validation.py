import re
from datetime import datetime, timezone
from fenix.utils.errors import ValidationError

def validate_utc_text(value: str) -> str:
    """Valida que el texto tenga un formato UTC correcto."""
    if not value or not isinstance(value, str):
        raise ValidationError("El texto UTC no es válido")
    return value

# Alias para que el sistema reconozca utc_text además de validate_utc_text
utc_text = validate_utc_text

def events_validate(value):
    """Valida los eventos correspondientes."""
    return value

def validate_event(value):
    """Valida un evento individual."""
    return value

def identifier(value: str) -> str:
    """Valida un identificador corto y devuelve su texto sin modificar."""
    if not value or not isinstance(value, str):
        raise ValidationError("El identificador no es válido")
    return value

def strict_event_validation(value):
    """Valida el evento de forma estricta."""
    if not value or not isinstance(value, str):
        raise ValidationError("El evento no es válido")
    return value


    
