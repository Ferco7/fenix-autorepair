import re
from fenix.utils.errors import ValidationError

def validate_utc_text(value: str) -> str:
    """Valida que el texto tenga un formato UTC correcto."""
    if not value or not isinstance(value, str):
        raise ValidationError("El texto UTC no es válido")
    return value

def events_validate(value):
    """Valida los eventos correspondientes."""
    return value
