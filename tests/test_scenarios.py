"""Escenarios ejecutables del integrante 6 sobre el flujo completo."""
import json
import time
import uuid
import warnings

import pytest
from botocore.exceptions import ClientError

from fenix.services import remediation, sqs as sqs_module, worker
from fenix.utils.errors import RetryableError
from fenix.utils.state import load, save


class FakeLogger:
    """Logger mínimo que conserva las líneas registradas por el worker."""

    def __init__(self):
        self.rows = []

    def _log(self, level, message, extra=None):
        self.rows.append((level, message, extra or {}))

    def info(self, message, extra=None):
        self._log("info", message, extra)

    def warning(self, message, extra=None):
        self._log("warning", message, extra)

    def error(self, message, extra=None):
        self._log("error", message, extra)


INVENTORY = {
    "_lab": {"group": "grupo01"},
    "node-01": {"type": "ec2", "id": "i-1", "security_group_id": "sg-1",
                "expected_tags": {}},
    "bucket-01": {"type": "s3", "id": "b-1", "expected_tags": {}},
}
EVENT = {
    "schema_version": 1,
    "event_id": "evt-001",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-10-22T18:00:00Z",
    "simulate_failures": 0,
}
MESSAGE = {"MessageId": "m-1", "ReceiptHandle": "r-1",
           "Body": json.dumps(EVENT)}


def preparar(tmp_path, monkeypatch):
    """Aísla inventario y ledger en tmp_path para no tocar data/ del grupo."""
    monkeypatch.chdir(tmp_path)
    save("data/inventory.json", INVENTORY)


def test_duplicate_is_idempotent(tmp_path, monkeypatch):
    """F11: repetir el mismo evento no repite reparación ni aviso."""
    preparar(tmp_path, monkeypatch)
    llamadas = {"repair": 0, "notify": 0}

    def fake_repair(resource, event_type):
        llamadas["repair"] += 1
        return "repaired"

    def fake_notify(text):
        llamadas["notify"] += 1

    monkeypatch.setattr(remediation, "repair", fake_repair)
    monkeypatch.setattr(remediation, "notify", fake_notify)

    remediation.handle(dict(EVENT))
    primero = load("data/events.json")["evt-001"]
    remediation.handle(dict(EVENT))  # Relee el ledger, como tras un reinicio.
    segundo = load("data/events.json")["evt-001"]

    assert llamadas == {"repair": 1, "notify": 1}
    assert segundo == primero
    assert segundo["repair_done"] is True
    assert segundo["notified"] is True
    assert segundo["status"] == "done"


def test_ack_is_after_success(monkeypatch):
    """F11/F12: un fallo no confirma; el éxito confirma solo al final."""
    orden = []
    monkeypatch.setattr(worker, "receive", lambda url: [dict(MESSAGE)])
    monkeypatch.setattr(worker, "acknowledge",
                        lambda url, receipt: orden.append("ack"))
    monkeypatch.setattr(worker, "retry_later",
                        lambda url, message: orden.append("retry"))

    def falla(event):
        orden.append("handler")
        raise RetryableError("falla transitoria")

    worker.run("url", falla, FakeLogger(), once=True)
    assert orden == ["handler", "retry"]  # Jamás se confirma un fallo.

    orden.clear()

    def funciona(event):
        orden.append("handler")

    worker.run("url", funciona, FakeLogger(), once=True)
    assert orden == ["handler", "ack"]  # El ACK ocurre después del éxito.


def test_restart_after_repair_only_notifies(tmp_path, monkeypatch):
    """F12: si repair_done ya está, el reinicio solo envía el aviso pendiente."""
    preparar(tmp_path, monkeypatch)
    contenido = json.dumps(EVENT, sort_keys=True, ensure_ascii=False)
    save("data/events.json", {"evt-001": {
        "content": contenido, "attempts": 1,
        "repair_done": True, "repair_result": "repaired",
        "notified": False, "status": "repaired",
    }})
    llamadas = {"repair": 0, "notify": 0}

    def fake_repair(resource, event_type):
        llamadas["repair"] += 1
        return "repaired"

    def fake_notify(text):
        llamadas["notify"] += 1

    monkeypatch.setattr(remediation, "repair", fake_repair)
    monkeypatch.setattr(remediation, "notify", fake_notify)

    remediation.handle(dict(EVENT))

    assert llamadas == {"repair": 0, "notify": 1}
    registro = load("data/events.json")["evt-001"]
    assert registro["notified"] is True
    assert registro["status"] == "done"


def _fast_retry(sqs):
    """Reintenta con visibilidad de un segundo para acortar la espera del test."""
    def reprogramar(url, message):
        sqs.change_message_visibility(
            QueueUrl=url, ReceiptHandle=message["ReceiptHandle"],
            VisibilityTimeout=1)
    return reprogramar


def _buscar_dlq(sqs, dead_url, deadline=3.0):
    """Busca un mensaje en la DLQ durante un plazo corto."""
    limite = time.monotonic() + deadline
    while time.monotonic() < limite:
        mensajes = sqs.receive_message(
            QueueUrl=dead_url, MaxNumberOfMessages=1,
            WaitTimeSeconds=1).get("Messages", [])
        if mensajes:
            return mensajes[0]
    return None


def _consumir_hasta_dlq(work_url, handler, logger, sqs, dead_url):
    """Consume la cola hasta que el redrive entregue el mensaje a la DLQ.

    LocalStack mueve el mensaje al agotar maxReceiveCount en una consulta
    posterior; por eso se alterna receive de la cola de trabajo y de la DLQ.
    """
    for _ in range(6):
        worker.run(work_url, handler, logger, once=True)
        mensaje = _buscar_dlq(sqs, dead_url)
        if mensaje is not None:
            return mensaje
    pytest.fail("El mensaje no llegó a la DLQ dentro del plazo")


def _borrar_colas(sqs, *urls):
    """Elimina solo las colas efímeras del ensayo, sin ocultar fallas."""
    for url in urls:
        if url is None:
            continue
        try:
            sqs.delete_queue(QueueUrl=url)
        except ClientError as error:
            warnings.warn(f"No se pudo eliminar la cola {url}: {error}",
                          stacklevel=1)


@pytest.mark.integracion
def test_redrive_with_localstack(monkeypatch):
    """F08: un JSON corrupto no mata al worker y termina en la DLQ real."""
    prefijo = f"fenix-i6-{uuid.uuid4().hex[:8]}"
    sqs = sqs_module.client("sqs")
    work_url = dead_url = None
    monkeypatch.setattr(worker, "retry_later", _fast_retry(sqs))
    try:
        work_url, dead_url = sqs_module.ensure_queues(prefijo)
        sqs.send_message(QueueUrl=work_url, MessageBody="{esto no es json")
        logger = FakeLogger()

        mensaje = _consumir_hasta_dlq(
            work_url, lambda event: pytest.fail("no debe procesar"),
            logger, sqs, dead_url)
        assert mensaje["Body"] == "{esto no es json"

        worker.run(work_url, lambda event: pytest.fail("no debe procesar"),
                   logger, once=True)  # La cola vacía no tumba al worker.
        assert any(nombre == "mensaje_reintentable"
                   for _, nombre, _ in logger.rows)
    finally:
        _borrar_colas(sqs, work_url, dead_url)


@pytest.mark.integracion
def test_persistent_failure_reaches_dlq(tmp_path, monkeypatch):
    """F10: una falla persistente agota maxReceiveCount y deriva a la DLQ."""
    prefijo = f"fenix-i6-{uuid.uuid4().hex[:8]}"
    sqs = sqs_module.client("sqs")
    work_url = dead_url = None
    monkeypatch.setattr(worker, "retry_later", _fast_retry(sqs))
    monkeypatch.setattr(remediation, "INVENTORY_PATH",
                        str(tmp_path / "inventory.json"))
    monkeypatch.setattr(remediation, "LEDGER_PATH",
                        str(tmp_path / "events.json"))
    save(remediation.INVENTORY_PATH, INVENTORY)
    evento = dict(EVENT, event_id="evt-f10", simulate_failures=5)
    acks = []
    monkeypatch.setattr(worker, "acknowledge",
                        lambda url, receipt: acks.append(receipt))
    try:
        work_url, dead_url = sqs_module.ensure_queues(prefijo)
        sqs.send_message(QueueUrl=work_url, MessageBody=json.dumps(evento))
        logger = FakeLogger()

        mensaje = _consumir_hasta_dlq(
            work_url, remediation.handle, logger, sqs, dead_url)

        assert acks == []  # Nunca se confirma un mensaje venenoso.
        assert json.loads(mensaje["Body"])["event_id"] == "evt-f10"

        registro = load(remediation.LEDGER_PATH)["evt-f10"]
        assert registro["attempts"] >= 3
        assert registro["repair_done"] is False
    finally:
        _borrar_colas(sqs, work_url, dead_url)
