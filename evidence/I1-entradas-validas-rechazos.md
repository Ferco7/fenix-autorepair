# I1 — Un evento correcto y tres rechazos sin publicación en SQS

- **Fecha:** 2026-11-17
- **Responsable:** I1 — Herrera, Nancy Mariel
- **Rama / commit:** `fix/tandas-0-3` / commit que acompaña este archivo
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux x86_64

## Preparación

```bash
docker compose up -d
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
```

## Comando

```bash
python - <<'PY'
import json, os, time, requests
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.services import sqs
from fenix.utils.crypto import signature

URL = "http://127.0.0.1:8000/webhook"
secret = os.environ["WEBHOOK_SECRET"]
queue = sqs.queue_url(os.environ["QUEUE_PREFIX"])
sqsc = sqs.client("sqs")

def pending():
    return int(sqsc.get_queue_attributes(
        QueueUrl=queue,
        AttributeNames=["ApproximateNumberOfMessages"],
    )["Attributes"]["ApproximateNumberOfMessages"])

def post(label, event):
    body = json.dumps(event, separators=(",", ":")).encode()
    ts = int(time.time())
    hdr = f"t={ts},v1={signature(secret, ts, body)}"
    r = requests.post(URL, data=body,
                      headers={"Content-Type": "application/json",
                               "X-Webhook-Signature": hdr},
                      timeout=(2, 15))
    print(label, r.status_code, r.text, "pendientes=", pending())

base = {
    "schema_version": 1,
    "event_id": "evt-i1-20261117-ok",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-11-17T12:00:00Z",
    "simulate_failures": 0,
}
post("valido", base)
post("extra", dict(base, event_id="evt-i1-rech-extra", extra="no"))
post("ajeno", dict(base, event_id="evt-i1-rech-ajeno", resource_id="node-99"))
post("bool", dict(base, event_id="evt-i1-rech-bool", schema_version=True))
PY
```

## Resultado esperado

- Un evento válido: **202** con `event_id` y `message_id`; la cola sube a 1.
- Tres rechazos: **422**; la cola permanece en 1 (no se publica nada nuevo).

## Resultado obtenido

```text
valido 202 {"status":"accepted","event_id":"evt-i1-20261117-ok","message_id":"5f386566-79cf-4a9a-ba9f-3348c07999fb"} pendientes= 1
extra 422 {"detail":"Evento no válido"} pendientes= 1
ajeno 422 {"detail":"Evento no válido"} pendientes= 1
bool 422 {"detail":"Evento no válido"} pendientes= 1
```

El mensaje válido se drenó al terminar la prueba para no dejar basura en la
cola del grupo.

## Qué verifica

Que I1 acepta un evento correcto y rechaza tres entradas inválidas antes de
publicar: clave extra, alias ajeno y `bool` en un campo entero. El contador de
SQS no cambia durante los rechazos.
