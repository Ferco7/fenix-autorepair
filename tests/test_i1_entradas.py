import pytest
from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, ttl_seconds, utc_text
from fenix.services.events import validate

INVENTORY = {
    "_lab": {"group": "grupo01"},
    "node-01": {"type": "ec2", "id": "i-1", "tags": {}},
    "bucket-01": {"type": "s3", "id": "b-1", "tags": {}},
}
EVENT = {
    "schema_version": 1,
    "event_id": "evt-001",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-10-22T18:00:00Z",
    "simulate_failures": 0,
}


def test_identifier_valido():
    assert identifier("grupo-01") == "grupo-01"


@pytest.mark.parametrize("valor", ["../ajeno", "MAYUS", "ab", "a" * 33, 123])
def test_identifier_invalido(valor):
    with pytest.raises(ValidationError):
        identifier(valor)


def test_ttl_limites():
    assert ttl_seconds("60") == 60
    assert ttl_seconds("600") == 600


@pytest.mark.parametrize("valor", ["59", "601", "60.5", "-60", "abc", 60])
def test_ttl_invalido(valor):
    with pytest.raises(ValidationError):
        ttl_seconds(valor)


def test_utc_valido():
    assert utc_text("2026-10-22T18:00:00Z").utcoffset().total_seconds() == 0


@pytest.mark.parametrize("valor", ["2026-10-22T18:00:00", "2026-10-22T18:00:00-03:00"])
def test_utc_invalido(valor):
    with pytest.raises(ValidationError):
        utc_text(valor)


def test_validate_ok():
    resultado = validate(dict(EVENT), INVENTORY)
    assert resultado == EVENT
    assert isinstance(resultado["occurred_at"], str)


def test_validate_rechaza_clave_extra():
    evento = dict(EVENT, extra="no")
    with pytest.raises(ValidationError):
        validate(evento, INVENTORY)


def test_validate_rechaza_bool_como_entero():
    evento = dict(EVENT, schema_version=True)
    with pytest.raises(ValidationError):
        validate(evento, INVENTORY)


def test_validate_rechaza_alias_desconocido():
    evento = dict(EVENT, resource_id="node-99")
    with pytest.raises(ValidationError):
        validate(evento, INVENTORY)


def test_validate_rechaza_tipo_incoherente():
    evento = dict(EVENT, event_type="bucket.tags_missing")
    with pytest.raises(ValidationError):
        validate(evento, INVENTORY)
