"""Pruebas del worker y del ledger durable (I5)."""
import json
import pytest
from botocore.exceptions import ClientError
from fenix.services import worker, remediation
from fenix.utils.errors import PermanentError, RetryableError
from fenix.utils.state import load, save


class FakeLogger:
    """Logger mínimo que conserva las líneas registradas."""

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
MESSAGE = {"MessageId": "m-1", "ReceiptHandle": "r-1",
           "Body": json.dumps(EVENT)}


def test_run_confirma_despues_del_handler(monkeypatch):
    """El ACK ocurre después de que el handler termina."""
    calls = []
    monkeypatch.setattr(worker, "receive", lambda url: [dict(MESSAGE)])
    monkeypatch.setattr(worker, "acknowledge",
                        lambda url, receipt: calls.append(("ack", receipt)))
    monkeypatch.setattr(worker, "retry_later",
                        lambda url, message: calls.append(("retry", message["MessageId"])))

    def handler(event):
        calls.append(("handler", event["event_id"]))

    worker.run("url", handler, FakeLogger(), once=True)
    assert calls == [("handler", "evt-001"), ("ack", "r-1")]


def test_run_no_confirma_si_el_handler_falla(monkeypatch):
    """Un handler fallido programa reintento y no confirma."""
    calls = []
    monkeypatch.setattr(worker, "receive", lambda url: [dict(MESSAGE)])
    monkeypatch.setattr(worker, "acknowledge",
                        lambda url, receipt: calls.append(("ack", receipt)))
    monkeypatch.setattr(worker, "retry_later",
                        lambda url, message: calls.append(("retry", message["MessageId"])))

    def handler(event):
        raise ValueError("fallo de negocio")

    worker.run("url", handler, FakeLogger(), once=True)
    assert calls == [("retry", "m-1")]


def test_run_sobrevive_a_json_corrupto(monkeypatch):
    """Un Body que no es JSON no mata el worker."""
    calls = []
    corrupto = dict(MESSAGE, Body="{no es json")
    monkeypatch.setattr(worker, "receive", lambda url: [corrupto])
    monkeypatch.setattr(worker, "acknowledge",
                        lambda url, receipt: calls.append(("ack", receipt)))
    monkeypatch.setattr(worker, "retry_later",
                        lambda url, message: calls.append(("retry", message["MessageId"])))

    worker.run("url", lambda event: None, FakeLogger(), once=True)
    assert calls == [("retry", "m-1")]


def test_run_once_sin_mensajes(monkeypatch):
    """once=True termina aunque la cola esté vacía."""
    calls = []
    monkeypatch.setattr(worker, "receive", lambda url: calls.append(url) or [])
    worker.run("url", lambda event: None, FakeLogger(), once=True)
    assert calls == ["url"]


def test_run_propaga_not_implemented(monkeypatch):
    """Una plantilla pendiente se propaga y nunca se confirma."""
    monkeypatch.setattr(worker, "receive", lambda url: [dict(MESSAGE)])
    monkeypatch.setattr(worker, "acknowledge",
                        lambda *args: pytest.fail("no debe confirmar"))
    monkeypatch.setattr(worker, "retry_later",
                        lambda *args: pytest.fail("no debe reintentar"))

    def handler(event):
        raise NotImplementedError("falta completar")

    with pytest.raises(NotImplementedError):
        worker.run("url", handler, FakeLogger(), once=True)


def test_run_sin_retry_si_falla_el_ack(monkeypatch):
    """Si el ACK falla, el mensaje queda disponible y no se reprograma."""
    calls = []

    def falla_ack(url, receipt):
        raise ClientError({"Error": {"Code": "InternalError", "Message": "x"}},
                          "DeleteMessage")

    monkeypatch.setattr(worker, "receive", lambda url: [dict(MESSAGE)])
    monkeypatch.setattr(worker, "acknowledge", falla_ack)
    monkeypatch.setattr(worker, "retry_later",
                        lambda url, message: calls.append("retry"))

    worker.run("url", lambda event: None, FakeLogger(), once=True)
    assert calls == []


def preparar(tmp_path, monkeypatch):
    """Prepara inventario y ledger aislados; usa el validate real de main."""
    monkeypatch.chdir(tmp_path)
    save("data/inventory.json", INVENTORY)


def test_handle_es_idempotente(tmp_path, monkeypatch):
    """Repetir el mismo evento no repite reparación ni aviso."""
    preparar(tmp_path, monkeypatch)
    calls = {"repair": 0, "notify": 0}

    def fake_repair(resource, event_type):
        calls["repair"] += 1
        return "repaired"

    def fake_notify(text):
        calls["notify"] += 1

    monkeypatch.setattr(remediation, "repair", fake_repair)
    monkeypatch.setattr(remediation, "notify", fake_notify)

    remediation.handle(dict(EVENT))
    remediation.handle(dict(EVENT))

    assert calls == {"repair": 1, "notify": 1}
    record = load("data/events.json")["evt-001"]
    assert record["repair_done"] is True
    assert record["repair_result"] == "repaired"
    assert record["notified"] is True
    assert record["status"] == "done"


def test_handle_respeta_simulate_failures(tmp_path, monkeypatch):
    """simulate_failures=2 agota dos intentos antes de reparar."""
    preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(remediation, "repair", lambda resource, event_type: "repaired")
    monkeypatch.setattr(remediation, "notify", lambda text: None)
    evento = dict(EVENT, simulate_failures=2)

    with pytest.raises(RetryableError):
        remediation.handle(dict(evento))
    with pytest.raises(RetryableError):
        remediation.handle(dict(evento))
    remediation.handle(dict(evento))

    record = load("data/events.json")["evt-001"]
    assert record["attempts"] == 3
    assert record["repair_done"] is True
    assert record["status"] == "done"


def test_handle_al_reiniciar_solo_notifica(tmp_path, monkeypatch):
    """Si repair_done ya está, solo notifica."""
    preparar(tmp_path, monkeypatch)
    contenido = json.dumps(EVENT, sort_keys=True, ensure_ascii=False)
    save("data/events.json", {"evt-001": {
        "content": contenido, "attempts": 1,
        "repair_done": True, "repair_result": "repaired",
        "notified": False, "status": "repaired",
    }})
    calls = {"repair": 0, "notify": 0}

    def fake_repair(resource, event_type):
        calls["repair"] += 1
        return "repaired"

    def fake_notify(text):
        calls["notify"] += 1

    monkeypatch.setattr(remediation, "repair", fake_repair)
    monkeypatch.setattr(remediation, "notify", fake_notify)

    remediation.handle(dict(EVENT))
    assert calls == {"repair": 0, "notify": 1}
    record = load("data/events.json")["evt-001"]
    assert record["notified"] is True
    assert record["status"] == "done"


def test_handle_rechaza_event_id_reutilizado(tmp_path, monkeypatch):
    """Mismo event_id con otro contenido es un error permanente."""
    preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(remediation, "repair", lambda resource, event_type: "repaired")
    monkeypatch.setattr(remediation, "notify", lambda text: None)

    remediation.handle(dict(EVENT))
    otro = dict(EVENT, event_type="bucket.tags_missing", resource_id="bucket-01")
    with pytest.raises(PermanentError):
        remediation.handle(otro)


def test_handle_preserva_otros_eventos(tmp_path, monkeypatch):
    """Actualizar un evento no borra los demás del ledger."""
    preparar(tmp_path, monkeypatch)
    save("data/events.json", {"otro-evento": {"content": "x"}})
    monkeypatch.setattr(remediation, "repair", lambda resource, event_type: "repaired")
    monkeypatch.setattr(remediation, "notify", lambda text: None)

    remediation.handle(dict(EVENT))
    ledger = load("data/events.json")
    assert "otro-evento" in ledger
    assert "evt-001" in ledger