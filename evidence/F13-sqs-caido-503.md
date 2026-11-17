# F13 — SQS detenido al recibir el webhook: 503 sin aceptación falsa

- **Fecha:** 2026-11-17
- **Responsable:** I2 — Maldonado, Fernando Manuel (revisión de I3)
- **Rama / commit:** `fix/tandas-0-3` / commit que acompaña este archivo
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux x86_64

## Preparación

```bash
docker compose up -d
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
```

Con el receptor ya levantado se detuvo el emulador para que `send_message`
fallara de verdad:

```bash
docker compose stop localstack
```

## Comando

```bash
python - <<'PY'
import json, os, time, requests
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.utils.crypto import signature

body = json.dumps({
    "schema_version": 1,
    "event_id": "evt-f13-20261117",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-11-17T12:00:00Z",
    "simulate_failures": 0,
}, separators=(",", ":")).encode()
ts = int(time.time())
hdr = f"t={ts},v1={signature(os.environ['WEBHOOK_SECRET'], ts, body)}"
r = requests.post("http://127.0.0.1:8000/webhook", data=body,
                  headers={"Content-Type": "application/json",
                           "X-Webhook-Signature": hdr},
                  timeout=(2, 15))
print(r.status_code, r.text)
PY
```

## Resultado esperado

HTTP **503** con `detail` de cola no disponible; nunca 202, porque `send_message`
no confirmó el almacenamiento.

## Resultado obtenido

```text
503 {"detail":"Cola no disponible"}
```

Después se reinició el emulador:

```bash
docker compose start localstack
```

## Qué verifica

Que el receptor no promete aceptación cuando SQS no confirmó el mensaje. El
código espera el `MessageId` de `send_message` antes de responder 202 y traduce
el fallo del SDK a 503.
