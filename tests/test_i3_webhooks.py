"""Contratos de I3: borde HTTP autenticado y reparaciones verificadas por API."""
import json
import time

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from fenix.services import receiver, remediation
from fenix.utils.crypto import signature, verify
from fenix.utils.errors import PermanentError, RetryableError, ValidationError


SECRET = "clave-ficticia-segura-para-pruebas"
EVENT = {
    "schema_version": 1,
    "event_id": "evt-001",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-10-22T18:00:00Z",
    "simulate_failures": 0,
}
INVENTORY = {
    "node-01": {"type": "ec2", "id": "i-test", "tags": {}},
    "bucket-01": {"type": "s3", "id": "bucket-test",
                  "tags": {"ManagedBy": "ppa2", "Owner": "grupo01"}},
}


def _signed(body: bytes, timestamp: int | None = None) -> dict[str, str]:
    """Devuelve las cabeceras para los mismos bytes que recibirá el endpoint."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    return {"X-Webhook-Signature":
            f"t={timestamp},v1={signature(SECRET, timestamp, body)}"}


class _Headers:
    """Modelo mínimo de Headers para ejercitar el manejador sin abrir un puerto."""

    def __init__(self, values: dict[str, str]):
        self.values = {key.lower(): value for key, value in values.items()}

    def get(self, key: str, default=None):
        return self.values.get(key.lower(), default)

    def getlist(self, key: str) -> list[str]:
        value = self.values.get(key.lower())
        return [] if value is None else [value]


class _Request:
    """Entrega un cuerpo HTTP de una vez, como lo hace el transporte de pruebas."""

    def __init__(self, body: bytes, headers: dict[str, str]):
        self.body = body
        self.headers = _Headers(headers)

    async def stream(self):
        yield self.body


class _Response:
    """Interfaz pequeña compatible con las aserciones de respuesta HTTP."""

    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class _EndpointClient:
    """Invoca el endpoint decorado y conserva sus códigos HTTP públicos."""

    def post(self, path: str, *, content: bytes, headers=None) -> _Response:
        assert path == "/webhook"
        try:
            operation = receiver.webhook(_Request(content, headers or {}))
            try:
                operation.send(None)
            except StopIteration as completed:
                payload = completed.value
            else:
                operation.close()
                raise AssertionError("El endpoint no debe suspenderse con estos fakes")
        except HTTPException as error:
            return _Response(error.status_code, {"detail": error.detail})
        return _Response(202, payload)


@pytest.fixture
def api_client(monkeypatch):
    """Construye un receptor local con las únicas variables necesarias."""
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("QUEUE_PREFIX", "fenix-test")
    return _EndpointClient()


def _prepare_receiver(monkeypatch, *, publish_result="msg-001") -> list[dict]:
    """Aísla inventario y SQS, conservando la validación real del endpoint."""
    sent: list[dict] = []
    monkeypatch.setattr(receiver, "load", lambda _: INVENTORY)
    monkeypatch.setattr(receiver, "queue_url", lambda _: "queue://test")

    async def run_synchronously(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(receiver, "run_in_threadpool", run_synchronously)

    def fake_publish(url: str, event: dict) -> str:
        assert url == "queue://test"
        sent.append(event)
        if isinstance(publish_result, Exception):
            raise publish_result
        return publish_result

    monkeypatch.setattr(receiver, "publish", fake_publish)
    return sent


@pytest.mark.pendiente
def test_webhook_rejects_invalid_signature_without_publishing(api_client, monkeypatch):
    """F04: una firma inválida responde 401 y nunca llega a SQS."""
    sent = _prepare_receiver(monkeypatch)
    body = json.dumps(EVENT).encode("utf-8")
    response = api_client.post("/webhook", content=body,
                               headers={"X-Webhook-Signature": "t=1,v1=" + "0" * 64})
    assert response.status_code == 401
    assert response.json()["detail"] == "Firma de webhook inválida"
    assert sent == []


@pytest.mark.pendiente
@pytest.mark.parametrize("header", [
    "t=1000,t=1000,v1=" + "0" * 64,
    "t=1000,v1=" + "0" * 63,
    "t=abc,v1=" + "0" * 64,
])
def test_verify_requires_one_strict_t_and_v1(header):
    """Rechaza encabezados ambiguos antes de comparar cualquier firma."""
    with pytest.raises(ValidationError, match="^Firma de webhook inválida$"):
        verify(SECRET, header, b"{}", now=1000)


@pytest.mark.pendiente
def test_webhook_parses_json_only_after_authentication(api_client, monkeypatch):
    """JSON roto pero firmado es 400; no firmado permanece opaco como 401."""
    sent = _prepare_receiver(monkeypatch)
    broken = b'{"schema_version":'
    response = api_client.post("/webhook", content=broken, headers=_signed(broken))
    assert response.status_code == 400
    assert sent == []

    response = api_client.post("/webhook", content=broken)
    assert response.status_code == 401
    assert sent == []


@pytest.mark.pendiente
def test_webhook_rejects_contract_and_unavailable_queue(api_client, monkeypatch):
    """El contrato es 422 y una publicación sin confirmar es 503, nunca 202."""
    sent = _prepare_receiver(monkeypatch)
    invalid = dict(EVENT, extra="no")
    body = json.dumps(invalid).encode("utf-8")
    response = api_client.post("/webhook", content=body, headers=_signed(body))
    assert response.status_code == 422
    assert sent == []

    unavailable = ClientError({"Error": {"Code": "ServiceUnavailable"},
                               "ResponseMetadata": {"HTTPStatusCode": 503}},
                              "SendMessage")
    _prepare_receiver(monkeypatch, publish_result=unavailable)
    valid = json.dumps(EVENT).encode("utf-8")
    response = api_client.post("/webhook", content=valid, headers=_signed(valid))
    assert response.status_code == 503


@pytest.mark.pendiente
def test_webhook_returns_202_only_after_sqs_message_id(api_client, monkeypatch):
    """La respuesta transporta el contexto de correlación del evento y de SQS."""
    sent = _prepare_receiver(monkeypatch)
    body = json.dumps(EVENT, separators=(",", ":")).encode("utf-8")
    response = api_client.post("/webhook", content=body, headers=_signed(body))
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "event_id": "evt-001",
                               "message_id": "msg-001"}
    assert sent == [EVENT]


@pytest.mark.pendiente
def test_webhook_limits_body_before_authentication(api_client, monkeypatch):
    """El límite se aplica aunque el atacante no conozca el secreto."""
    sent = _prepare_receiver(monkeypatch)
    response = api_client.post("/webhook", content=b"x" * (16 * 1024 + 1))
    assert response.status_code == 413
    assert sent == []


class FakeEC2:
    """Cliente pequeño que permite observar el describe posterior al start."""

    def __init__(self, state: str):
        self.state = state
        self.starts: list[list[str]] = []
        self.describes = 0

    def describe_instances(self, *, InstanceIds):
        self.describes += 1
        return {"Reservations": [{"Instances": [{"InstanceId": InstanceIds[0],
                                                     "State": {"Name": self.state}}]}]}

    def start_instances(self, *, InstanceIds):
        self.starts.append(InstanceIds)
        self.state = "running"
        return {"StartingInstances": []}


class FakeS3:
    """Cliente que reemplaza tags como S3 y conserva las lecturas hechas."""

    def __init__(self, tags: dict[str, str]):
        self.tags = dict(tags)
        self.puts: list[dict] = []
        self.reads = 0

    def get_bucket_tagging(self, *, Bucket):
        self.reads += 1
        return {"TagSet": [{"Key": key, "Value": value}
                            for key, value in self.tags.items()]}

    def put_bucket_tagging(self, *, Bucket, Tagging):
        self.puts.append(Tagging)
        self.tags = {tag["Key"]: tag["Value"] for tag in Tagging["TagSet"]}
        return {}


@pytest.mark.pendiente
def test_repair_starts_stopped_instance_and_rechecks_running(monkeypatch):
    """F02: stopped -> start_instances -> describe = running por API."""
    ec2 = FakeEC2("stopped")
    monkeypatch.setattr(remediation, "client", lambda service: ec2)
    result = remediation.repair(INVENTORY["node-01"], "instance.stopped")
    assert result == "repaired"
    assert ec2.starts == [["i-test"]]
    assert ec2.describes == 2
    assert ec2.state == "running"


@pytest.mark.pendiente
def test_repair_merges_tags_and_verifies_s3_result(monkeypatch):
    """F03: agrega las obligatorias, conserva ajenas y relee el bucket."""
    s3 = FakeS3({"Foreign": "keep", "ManagedBy": "ppa2"})
    monkeypatch.setattr(remediation, "client", lambda service: s3)
    result = remediation.repair(INVENTORY["bucket-01"], "bucket.tags_missing")
    assert result == "repaired"
    assert s3.tags == {"Foreign": "keep", "ManagedBy": "ppa2", "Owner": "grupo01"}
    assert len(s3.puts) == 1
    assert s3.reads == 2


@pytest.mark.pendiente
def test_repair_classifies_instance_state(monkeypatch):
    """pending se reintenta y terminated no puede repararse con un start."""
    pending = FakeEC2("pending")
    monkeypatch.setattr(remediation, "client", lambda service: pending)
    with pytest.raises(RetryableError):
        remediation.repair(INVENTORY["node-01"], "instance.stopped")

    terminated = FakeEC2("terminated")
    monkeypatch.setattr(remediation, "client", lambda service: terminated)
    with pytest.raises(PermanentError):
        remediation.repair(INVENTORY["node-01"], "instance.stopped")
