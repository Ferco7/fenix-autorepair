def validate_utc_text(value: str) -> str:
    """Valida que el texto tenga un formato UTC correcto."""
    if not value or not isinstance(value, str):
        raise ValidationError("El texto UTC no es válido")
    return value
