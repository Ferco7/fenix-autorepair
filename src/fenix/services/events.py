"""Contrato de eventos de autorreparación; integrante 1."""
from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, utc_text

EVENT_TYPES = {
    "instance.stopped": "ec2",
    "bucket.tags_missing": "s3",
}
FIELDS = {
    "schema_version",
    "event_id",
    "event_type",
    "resource_id",
    "occurred_at",
    "simulate_failures",
}


def validate(event: dict, inventory: dict) -> dict:
    """Valida esquema cerrado y resuelve exclusivamente aliases autorizados."""
    if not isinstance(event, dict):
        raise ValidationError("El evento debe ser un objeto JSON")
    if not isinstance(inventory, dict):
        raise ValidationError("El inventario debe ser un objeto")

    if set(event) != FIELDS:
        raise ValidationError("El evento no cumple el esquema cerrado")

    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        raise ValidationError("schema_version debe ser el entero 1")

    identifier(event["event_id"])
    resource_id = identifier(event["resource_id"])

    event_type = event["event_type"]
    if event_type not in EVENT_TYPES:
        raise ValidationError("event_type no permitido")

    utc_text(event["occurred_at"])

    failures = event["simulate_failures"]
    if type(failures) is not int or not 0 <= failures <= 5:
        raise ValidationError("simulate_failures debe ser un entero entre 0 y 5")

    resource = inventory.get(resource_id)
    if not isinstance(resource, dict):
        raise ValidationError("resource_id no pertenece al inventario")
    if resource.get("type") != EVENT_TYPES[event_type]:
        raise ValidationError("event_type no coincide con el recurso")

    return dict(event)

