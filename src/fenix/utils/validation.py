from datetime import datetime
from fenix.utils.errors import ValidationError, DomainError

def validate_utc_text(utc_text):
    """Valida que el texto cumpla con el formato de fecha y hora UTC (ISO 8601)."""
    if not isinstance(utc_text, str):
        return False
    try:
        datetime.fromisoformat(utc_text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

def events_validate(data):
    """
    Valida el identificador, formato UTC y estructura general del dominio.
    Rechaza listas u objetos incorrectos.
    """
    if not isinstance(data, dict):
        raise ValidationError("El evento debe ser un objeto JSON válido (diccionario). No se permiten listas.")
    
    identifier = data.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValidationError("El campo 'identifier' es obligatorio y debe ser un texto válido.")
        
    utc_text = data.get("utc_text")
    if not validate_utc_text(utc_text):
        raise ValidationError("El campo 'utc_text' es obligatorio y debe tener un formato UTC válido.")
        
    return True

def strict_event_validation(payload, allowed_event_types, valid_resource_ids):
    """
    Realiza una validación estricta:
    - Rechaza claves extra o ausentes.
    - Rechaza bool como entero.
    - Valida event_type y resource_id.
    - Integra ttl_seconds como práctica del helper.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Objeto incorrecto: Se esperaba un diccionario JSON.")

    allowed_keys = {"identifier", "utc_text", "event_type", "resource_id", "active_status", "ttl_seconds"}
    payload_keys = set(payload.keys())

    missing_keys = allowed_keys - payload_keys
    extra_keys = payload_keys - allowed_keys
    
    if missing_keys:
        raise ValidationError(f"Claves ausentes en el objeto: {missing_keys}")
    if extra_keys:
        raise ValidationError(f"Claves extra no permitidas detectadas: {extra_keys}")

    if "active_status" in payload:
        val = payload["active_status"]
        if type(val) is not bool:
            raise ValidationError("El campo 'active_status' debe ser estrictamente de tipo booleano (no entero).")

    event_type = payload.get("event_type")
    if event_type not in allowed_event_types:
        raise DomainError(f"El tipo de evento '{event_type}' es desconocido o no permitido.")

    resource_id = payload.get("resource_id")
    if resource_id not in valid_resource_ids:
        raise DomainError(f"El resource_id '{resource_id}' es ajeno o no pertenece al inventario autorizado.")

    ttl_seconds = payload.get("ttl_seconds", 3600)
    if not isinstance(ttl_seconds, int) or ttl_seconds < 0:
        raise ValidationError("El campo 'ttl_seconds' debe ser un número entero positivo.")

    return True
