# O1 — Logs JSON de un evento nominal y de un mensaje corrupto

- **Fecha:** 2026-11-17
- **Responsable:** I4 — Alegre, Facundo Sebastián
- **Rama / commit:** `fix/tandas-0-3` / commit que acompaña este archivo
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux x86_64

## Preparación

```bash
docker compose up -d
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli fault node-01
```

## 1. Evento nominal

Se publicó un evento válido y se procesó con una sola pasada del worker:

```bash
python - <<'PY'
import json, os, time
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.services import sqs

url = sqs.queue_url(os.environ["QUEUE_PREFIX"])
event = {
    "schema_version": 1,
    "event_id": "evt-log-nominal-1794931949",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "simulate_failures": 0,
}
print(sqs.publish(url, event))
PY

python -m fenix.cli worker --once
```

Archivo completo: [`O1-log-nominal.jsonl`](O1-log-nominal.jsonl) (9 líneas).
Cada línea corresponde a un paso y conserva `event_id`, `resource_id`,
`action`, `attempt`, `status`, `message_id`, `process` y `timestamp` UTC.

Extracto real:

```json
{"timestamp": "2026-11-17T16:12:29.791807+00:00", "level": "INFO", "message": "event_received", "process": 24670, "thread": "MainThread", "event_id": "evt-log-nominal-1794931949", "message_id": null, "resource_id": "node-01", "attempt": null, "action": "instance.stopped", "status": "received"}
{"timestamp": "2026-11-17T16:12:29.847301+00:00", "level": "INFO", "message": "repair_verified", "process": 24670, "thread": "MainThread", "event_id": "evt-log-nominal-1794931949", "message_id": null, "resource_id": "i-b13c148e654d2b2fd", "attempt": null, "action": "instance.stopped", "status": "repaired"}
{"timestamp": "2026-11-17T16:12:29.852266+00:00", "level": "INFO", "message": "mensaje_confirmado", "process": 24670, "thread": "MainThread", "event_id": "evt-log-nominal-1794931949", "message_id": "d0e7a3bc-6ce4-477b-af36-7fd4f75985ad", "resource_id": "node-01", "attempt": 1, "action": "instance.stopped", "status": "acknowledged"}
```

La secuencia `event_received` → `attempt_registered` → `repair_started` →
`repair_verified` → `repair_done` → `notify_started` → `notify_confirmed` →
`event_done` → `mensaje_confirmado` permite seguir el evento sin leer el cuerpo
del mensaje ni el ledger.

## 2. Mensaje corrupto inyectado directo a SQS

Se envió a la cola un cuerpo que no es JSON y se ejecutó el worker:

```bash
python - <<'PY'
import os
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.services import sqs

url = sqs.queue_url(os.environ["QUEUE_PREFIX"])
print(sqs.client("sqs").send_message(
    QueueUrl=url, MessageBody="{esto no es json")["MessageId"])
PY

python -m fenix.cli worker --once
```

Archivo completo: [`O1-log-fallo.jsonl`](O1-log-fallo.jsonl) (1 línea).

```json
{"timestamp": "2026-11-17T16:12:39.350257+00:00", "level": "ERROR", "message": "mensaje_reintentable", "process": 24730, "thread": "MainThread", "event_id": null, "message_id": "74ba7f9e-d5f1-4eb5-bbd9-599767e786c3", "resource_id": null, "attempt": 1, "action": null, "status": "JSONDecodeError"}
```

El worker no se detuvo: registró el `message_id` y el tipo de error, y dejó el
mensaje para el reintento y la DLQ. `event_id` queda en `null` porque el cuerpo
todavía no se pudo decodificar.

## Qué verifica

- Una línea JSON por registro, con los campos de contexto (`event_id`,
  `resource_id`, `action`, `attempt`, `status`) y `timestamp` con offset UTC.
- El flujo nominal deja nueve líneas y termina en `status=acknowledged`.
- Un cuerpo corrupto produce `ERROR` con `status=JSONDecodeError`, conserva el
  `message_id` y no imprime secretos ni el cuerpo crudo.
