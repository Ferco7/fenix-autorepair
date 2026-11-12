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
    data = []
    assert events_validate(data) is False
