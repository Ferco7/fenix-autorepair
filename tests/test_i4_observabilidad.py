"""Pruebas de notificaciones, logs y rotación (I4)."""
import gzip
import json
import logging
import logging.handlers

import pytest
import requests

from fenix.services import notifications, remediation
from fenix.utils import logging_json
from fenix.utils.errors import PermanentError, RetryableError
from fenix.utils.state import load, save


class FakeResponse:
    """Respuesta HTTP mínima con status, cuerpo y encabezados controlados."""

    def __init__(self, status_code=200, payload=None, text="ok", headers=None,
                 json_error=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.text = text
        self.headers = headers or {}
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("cuerpo no JSON")
        return self._payload


class FakeClock:
    """Sustituye time.sleep y conserva las esperas pedidas."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def preparar_telegram(monkeypatch):
    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-secreto-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")


def preparar_slack(monkeypatch):
    monkeypatch.setenv("NOTIFY_PROVIDER", "slack")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/xxx")


def test_console_no_usa_red(monkeypatch, capsys):
    """El modo console imprime y no intenta contactar a ningún proveedor."""
    monkeypatch.setenv("NOTIFY_PROVIDER", "console")

    def prohibido(*args, **kwargs):
        raise AssertionError("console no debe usar red")

    monkeypatch.setattr(notifications.requests, "post", prohibido)
    notifications.notify("aviso de prueba")
    assert capsys.readouterr().out.strip() == "aviso de prueba"


def test_telegram_envia_y_acepta_ok(monkeypatch):
    """Telegram con status 200 y ok true confirma el envío."""
    preparar_telegram(monkeypatch)
    capturado = {}

    def fake_post(url, json=None, timeout=None):
        capturado.update(url=url, payload=json, timeout=timeout)
        return FakeResponse(status_code=200, payload={"ok": True})

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    notifications.notify("reparado node-01")

    assert capturado["url"].endswith("/sendMessage")
    assert capturado["payload"] == {"chat_id": "42", "text": "reparado node-01"}
    assert capturado["timeout"] == (2, 5)


def test_telegram_ok_false_es_permanente(monkeypatch):
    """HTTP 200 con ok=false es un rechazo funcional y no se reintenta."""
    preparar_telegram(monkeypatch)
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: FakeResponse(payload={"ok": False,
                                                              "description": "chat not found"}))
    with pytest.raises(PermanentError):
        notifications.notify("aviso")


def test_telegram_json_ilegible_es_permanente(monkeypatch):
    """Un cuerpo que no es JSON no se interpreta como éxito."""
    preparar_telegram(monkeypatch)
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: FakeResponse(json_error=True))
    with pytest.raises(PermanentError):
        notifications.notify("aviso")


@pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError()])
def test_errores_de_red_son_reintentables(monkeypatch, error):
    """Timeout y conexión se traducen a RetryableError."""
    preparar_telegram(monkeypatch)

    def fake_post(*args, **kwargs):
        raise error

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    with pytest.raises(RetryableError):
        notifications.notify("aviso")


def test_429_espera_acotada_y_reintenta(monkeypatch):
    """Retry-After mayor al tope se recorta a 30 segundos."""
    preparar_telegram(monkeypatch)
    reloj = FakeClock()
    monkeypatch.setattr(notifications.time, "sleep", reloj)
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: FakeResponse(status_code=429,
                                                     headers={"Retry-After": "120"}))

    with pytest.raises(RetryableError):
        notifications.notify("aviso")
    assert reloj.delays == [30]


def test_429_sin_retry_after_no_espera(monkeypatch):
    """Un 429 sin encabezado válido no bloquea al worker."""
    preparar_telegram(monkeypatch)
    reloj = FakeClock()
    monkeypatch.setattr(notifications.time, "sleep", reloj)
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: FakeResponse(status_code=429,
                                                     headers={"Retry-After": "pronto"}))

    with pytest.raises(RetryableError):
        notifications.notify("aviso")
    assert reloj.delays == []


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_es_reintentable(monkeypatch, status):
    """Los errores del servidor del proveedor se reintentan."""
    preparar_telegram(monkeypatch)
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: FakeResponse(status_code=status))
    with pytest.raises(RetryableError):
        notifications.notify("aviso")


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_4xx_es_permanente(monkeypatch, status):
    """Credenciales o payload inválidos no se reintentan para siempre."""
    preparar_telegram(monkeypatch)
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: FakeResponse(status_code=status))
    with pytest.raises(PermanentError):
        notifications.notify("aviso")


def test_slack_envia_y_acepta_ok(monkeypatch):
    """Slack confirma con status 200 y cuerpo "ok"."""
    preparar_slack(monkeypatch)
    capturado = {}

    def fake_post(url, json=None, timeout=None):
        capturado.update(url=url, payload=json, timeout=timeout)
        return FakeResponse(status_code=200, text="ok")

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    notifications.notify("reparado bucket-01")
    assert capturado["payload"] == {"text": "reparado bucket-01"}
    assert capturado["timeout"] == (2, 5)


def test_slack_cuerpo_distinto_es_permanente(monkeypatch):
    """Slack puede responder 200 con un cuerpo de error."""
    preparar_slack(monkeypatch)
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: FakeResponse(status_code=200,
                                                     text="invalid_payload"))
    with pytest.raises(PermanentError):
        notifications.notify("aviso")


def test_configuracion_faltante_es_permanente(monkeypatch):
    """Sin credenciales no se intenta la llamada HTTP."""
    monkeypatch.setenv("NOTIFY_PROVIDER", "telegram")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(notifications.requests, "post",
                        lambda *a, **k: pytest.fail("no debe llamar sin token"))
    with pytest.raises(PermanentError):
        notifications.notify("aviso")


def test_proveedor_desconocido_es_permanente(monkeypatch):
    """Un NOTIFY_PROVIDER no soportado es un error de configuración."""
    monkeypatch.setenv("NOTIFY_PROVIDER", "paloma-mensajera")
    with pytest.raises(PermanentError):
        notifications.notify("aviso")


def test_el_error_no_expone_el_token(monkeypatch):
    """El mensaje público no copia la URL del proveedor."""
    preparar_telegram(monkeypatch)

    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("https://api.telegram.org/bottoken-secreto-123/x")

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    with pytest.raises(RetryableError) as excinfo:
        notifications.notify("aviso")
    assert "token-secreto-123" not in str(excinfo.value)


def test_texto_se_recorta_a_1000(monkeypatch):
    """El resumen enviado nunca supera el límite público."""
    preparar_telegram(monkeypatch)
    capturado = {}

    def fake_post(url, json=None, timeout=None):
        capturado.update(json)
        return FakeResponse(status_code=200, payload={"ok": True})

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    notifications.notify("x" * 5000)
    assert capturado["text"] == "x" * 1000


def test_json_formatter_incluye_contexto_y_nulos():
    """Cada línea JSON conserva los campos autorizados y completa con null."""
    record = logging.LogRecord("fenix-i4", logging.INFO, __file__, 1,
                               "aviso %s", ("enviado",), None)
    record.event_id = "evt-1"
    record.message_id = "m-1"
    record.resource_id = "node-01"
    record.attempt = 2
    record.action = "instance.stopped"
    record.status = "done"

    record.token = "token-secreto-123"  # Extra fuera de la lista cerrada.

    fila = json.loads(logging_json.JSONFormatter().format(record))
    assert fila["timestamp"].endswith("+00:00")
    assert "token-secreto-123" not in json.dumps(fila)
    assert fila["message"] == "aviso enviado"
    assert fila["level"] == "INFO"
    assert fila["event_id"] == "evt-1"
    assert fila["message_id"] == "m-1"
    assert fila["resource_id"] == "node-01"
    assert fila["attempt"] == 2
    assert fila["action"] == "instance.stopped"
    assert fila["status"] == "done"


def test_formatter_completa_campos_ausentes_con_null():
    """Un log sin contexto mantiene el mismo contrato de campos."""
    record = logging.LogRecord("fenix-i4", logging.WARNING, __file__, 2,
                               "sin contexto", (), None)
    fila = json.loads(logging_json.JSONFormatter().format(record))
    assert fila["event_id"] is None
    assert fila["attempt"] is None
    assert fila["status"] is None


def test_setup_escribe_json_con_contexto(tmp_path, monkeypatch):
    """El pipeline real escribe una línea JSON por registro en logs/."""
    monkeypatch.chdir(tmp_path)
    logger, listener = logging_json.setup("fenix-i4-test")
    try:
        logger.info("aviso enviado", extra={"event_id": "evt-1",
                                            "resource_id": "node-01",
                                            "attempt": 1,
                                            "action": "instance.stopped",
                                            "status": "done"})
    finally:
        listener.stop()

    archivos = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(archivos) == 1
    fila = json.loads(archivos[0].read_text(encoding="utf-8").strip())
    assert fila["message"] == "aviso enviado"
    assert fila["event_id"] == "evt-1"
    assert fila["attempt"] == 1


def test_rotacion_gzip_comprime_y_borra(tmp_path):
    """Al rotar, el histórico queda comprimido y el original desaparece."""
    destino = tmp_path / "app.jsonl"
    handler = logging.handlers.RotatingFileHandler(destino, maxBytes=300,
                                                   backupCount=1,
                                                   encoding="utf-8")
    handler.setFormatter(logging_json.JSONFormatter())
    handler.namer, handler.rotator = logging_json.gzip_name, logging_json.gzip_rotate

    logger = logging.getLogger("fenix-i4-rotacion")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        for numero in range(20):
            logger.info("linea %s", numero, extra={"event_id": f"evt-{numero}"})
    finally:
        handler.close()

    comprimido = tmp_path / "app.jsonl.1.gz"
    assert comprimido.exists()
    assert not (tmp_path / "app.jsonl.1").exists()
    with gzip.open(comprimido, "rt", encoding="utf-8") as archivo:
        filas = [json.loads(linea) for linea in archivo]
    assert filas
    assert all(fila["event_id"] for fila in filas)
    assert all(fila["timestamp"].endswith("+00:00") for fila in filas)


EVENT = {
    "schema_version": 1,
    "event_id": "evt-001",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-10-22T18:00:00Z",
    "simulate_failures": 0,
}


def test_f14_429_no_repite_reparacion(tmp_path, monkeypatch):
    """Un 429 al notificar reintenta solo el aviso, no la reparación."""
    monkeypatch.chdir(tmp_path)
    save("data/inventory.json", {
        "node-01": {"type": "ec2", "id": "i-1", "security_group_id": "sg-1",
                    "expected_tags": {}},
    })

    llamadas = {"repair": 0, "notify": 0}

    def fake_repair(resource, event_type):
        llamadas["repair"] += 1
        return "repaired"

    def fake_notify(text):
        llamadas["notify"] += 1
        if llamadas["notify"] == 1:
            raise RetryableError("El proveedor limitó el envío (429); reintentar")

    monkeypatch.setattr(remediation, "repair", fake_repair)
    monkeypatch.setattr(remediation, "notify", fake_notify)

    with pytest.raises(RetryableError):
        remediation.handle(dict(EVENT))
    remediation.handle(dict(EVENT))

    assert llamadas == {"repair": 1, "notify": 2}
    registro = load("data/events.json")["evt-001"]
    assert registro["repair_result"] == "repaired"
    assert registro["notified"] is True
    assert registro["status"] == "done"