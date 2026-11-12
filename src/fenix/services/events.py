from fenix.utils.errors import ValidationError
from fenix.utils.validation import strict_event_validation

def process_incoming_event(event):
    """Procesa el evento entrante de forma segura."""
    if not event:
        raise ValidationError("El evento entrante no es válido")
    return strict_event_validation(event)
