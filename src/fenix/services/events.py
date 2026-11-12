from fenix.utils.validation import events_validate, strict_event_validation
from fenix.utils.errors import ValidationError, DomainError

def process_incoming_event(raw_event, inventory_database):
    """
    Función del servicio de eventos para Integrante 1.
    Entradas: raw_event (evento recibido), inventory_database (inventario permitido).
    Salida: Copia validada del evento o lanza una excepción si hay errores.
    """
    allowed_types = {"CREATE", "UPDATE", "DELETE", "SYNC"}
    
    try:
        events_validate(raw_event)
        strict_event_validation(raw_event, allowed_types, inventory_database)
        
        validated_copy = dict(raw_event)
        validated_copy["validation_status"] = "APPROVED"
        return validated_copy

    except (ValidationError, DomainError) as e:
        raise ValidationError(f"Fallo de validación de entrada - Evento descartado localmente: {str(e)}")
