import pytest
from datetime import datetime
from fenix.utils.errors import ValidationError, DomainError
from fenix.utils.validation import validate_utc_text, events_validate, strict_event_validation
from fenix.services.events import process_incoming_event

def test_validate_utc_text_valid():
    assert validate_utc_text("2026-11-12T14:00:00Z") is True

def test_validate_utc_text_invalid():
    assert validate_utc_text("fecha-invalida") is False
    assert validate_utc_text(12345) is False

def test_events_validate_success():
    data = {
        "identifier": "EVT-001",
        "utc_text": "2026-11-12T14:00:00Z"
    }
    assert events_validate(data) is True

def test_events_validate_rejects_list():
    with pytest.raises(ValidationError):
        events_validate(["no", "es", "un", "dict"])

def test_strict_event_validation_success():
    payload = {
        "identifier": "EVT-001",
        "utc_text": "2026-11-12T14:00:00Z",
        "event_type": "CREATE",
        "resource_id": "RES-01",
        "active_status": True,
        "ttl_seconds": 3600
    }
    allowed_types = {"CREATE", "UPDATE", "DELETE", "SYNC"}
    valid_resources = {"RES-01", "RES-02"}
    
    assert strict_event_validation(payload, allowed_types, valid_resources) is True

def test_strict_event_validation_rejects_bool_as_int():
    payload = {
        "identifier": "EVT-001",
        "utc_text": "2026-11-12T14:00:00Z",
        "event_type": "CREATE",
        "resource_id": "RES-01",
        "active_status": 1, # Inválido: entero en lugar de bool estricto
        "ttl_seconds": 3600
    }
    allowed_types = {"CREATE"}
    valid_resources = {"RES-01"}
    
    with pytest.raises(ValidationError):
        strict_event_validation(payload, allowed_types, valid_resources)

def test_process_incoming_event_discards_on_error():
    invalid_event = {
        "identifier": "EVT-999",
        "utc_text": "2026-11-12T14:00:00Z",
        "event_type": "UNKNOWN_TYPE",
        "resource_id": "RES-01",
        "active_status": True
    }
    inventory = {"RES-01"}
    
    # Debe lanzar excepción local y no procesar ni publicar nada
    with pytest.raises(ValidationError):
        process_incoming_event(invalid_event, inventory)
