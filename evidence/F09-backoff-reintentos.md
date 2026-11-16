# F09 — Backoff 2 y 4 con `simulate_failures=2`

- **Fecha:** 2026-11-15
- **Responsable:** I2 — Maldonado, Fernando Manuel
- **Rama / commit:** `main` = `04f5daf`
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux 7.0.0 x86_64

## Preparación

```bash
docker compose up -d
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli fault node-01
```

Salida real:

```text
$ python -m fenix.cli fault node-01
$ python - <<'PY'   # describe_instances sobre node-01
...
estado: stopped
```

## Comando

Publicación de un evento nuevo directo a SQS (sin receptor, para aislar el
comportamiento del worker):

```bash
python - <<'PY'
import json, os, time
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.services import sqs

url = sqs.queue_url(os.environ["QUEUE_PREFIX"])
event = {
    "schema_version": 1,
    "event_id": "evt-f09-20261115b",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "simulate_failures": 2,
}
r = sqs.client("sqs").send_message(QueueUrl=url,
                                   MessageBody=json.dumps(event))
print("publicado:", r["MessageId"])
print("body:", json.dumps(event))
PY
```

Consumo con esperas mayores que los backoff de 2 y 4 segundos:

```bash
python -m fenix.cli worker --once
sleep 3
python -m fenix.cli worker --once
sleep 5
python -m fenix.cli worker --once
```

## Resultado esperado

Los dos primeros intentos fallan antes de reparar y reprograman el mensaje con
visibilidad de 2 y 4 segundos. El tercer intento repara, avisa y confirma.

## Resultado obtenido

### Publicación

```text
publicado: 674a34b2-d04f-43c6-9270-60bf92d0b7aa
body: {"schema_version": 1, "event_id": "evt-f09-20261115b", "event_type": "instance.stopped", "resource_id": "node-01", "occurred_at": "2026-11-16T01:49:54Z", "simulate_failures": 2}
```

### Ledger después de cada intento

```text
{"attempts": 1, "repair_done": false, "repair_result": null, "notified": false, "status": "retrying"}
{"attempts": 2, "repair_done": false, "repair_result": null, "notified": false, "status": "retrying"}
{"attempts": 3, "repair_done": true, "repair_result": "repaired", "notified": true, "status": "done"}
```

### Logs del worker

```text
{"timestamp": "2026-11-16T01:49:58.094241+00:00", "level": "ERROR", "message": "mensaje_reintentable", "process": 23408, "thread": "MainThread", "event_id": "evt-f09-20261115b", "message_id": "674a34b2-d04f-43c6-9270-60bf92d0b7aa", "resource_id": "node-01", "attempt": 1, "action": "instance.stopped", "status": "RetryableError"}
{"timestamp": "2026-11-16T01:50:01.299259+00:00", "level": "ERROR", "message": "mensaje_reintentable", "process": 23432, "thread": "MainThread", "event_id": "evt-f09-20261115b", "message_id": "674a34b2-d04f-43c6-9270-60bf92d0b7aa", "resource_id": "node-01", "attempt": 2, "action": "instance.stopped", "status": "RetryableError"}
{"timestamp": "2026-11-16T01:50:06.560658+00:00", "level": "INFO", "message": "mensaje_confirmado", "process": 23474, "thread": "MainThread", "event_id": "evt-f09-20261115b", "message_id": "674a34b2-d04f-43c6-9270-60bf92d0b7aa", "resource_id": "node-01", "attempt": 3, "action": "instance.stopped", "status": "acknowledged"}
```

Las diferencias entre intentos son 3,2 s y 5,3 s; incluyen el arranque de cada
proceso CLI. La visibilidad aplicada por `retry_later` fue de 2 s y 4 s, según
`min(30, 2 ** ApproximateReceiveCount)`.

### Verificación con el SDK

```text
instance: i-106dd7415c5c95734 running
work attrs: {"ApproximateNumberOfMessages": "0", "ApproximateNumberOfMessagesNotVisible": "0"}
ledger F09: {"attempts": 3, "repair_done": true, "repair_result": "repaired", "notified": true, "status": "done"}
```

## Evidencia

- Salida real transcripta arriba; no se adjunta captura.
- Logs de runtime: `logs/fenix-worker-<pid>.jsonl` (gitignored, no se versionan).

## Observaciones

- `retry_later` cambia la visibilidad del mensaje original; no hace `send_message`
  ni reinicia `ApproximateReceiveCount`.
- El ACK se ejecuta recién en el tercer intento, después de reparar y avisar.
  El log de confirmación registra `status="acknowledged"`.
- `notify` se ejecutó en modo `console` (default local); no se envió nada a
  Telegram para esta prueba.
- El nodo quedó en `running` verificado por `describe_instances`, no solo por el
  log del worker.
