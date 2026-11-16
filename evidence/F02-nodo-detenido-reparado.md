# F02 — Nodo detenido → alerta válida → `running` verificado por API

- **Fecha:** 16/11/2026
- **Responsable:** I3 — Mamani, Hector Mauricio
- **Rama / commit:** `main` = `a30b45b`
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3

## Preparación

```bash
docker compose up -d
python scripts/doctor.py
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli fault node-01
```

Estado inicial leído con el SDK (debe ser `stopped`):

```bash
python - <<'PY'
import json
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.config.settings import client
inv = json.load(open("data/inventory.json", encoding="utf-8"))
iid = inv["node-01"]["id"]
state = client("ec2").describe_instances(InstanceIds=[iid])[
    "Reservations"][0]["Instances"][0]["State"]["Name"]
print("instance:", iid, state)
PY
```

Evento nuevo con `event_id` único (se guarda en `data/`, que Git ignora):

```bash
python - <<'PY'
import json, time
event = {"schema_version": 1, "event_id": "evt-f02-" + time.strftime("%Y%m%d%H%M"),
         "event_type": "instance.stopped", "resource_id": "node-01",
         "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "simulate_failures": 0}
json.dump(event, open("data/f02-event.json", "w", encoding="utf-8"), indent=2)
print(json.dumps(event))
PY
```

Receptor en otra terminal:

```bash
python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
```

## Comando

### 1. Prueba automática (sin LocalStack)

```bash
pytest tests/test_i3_webhooks.py::test_repair_starts_stopped_instance_and_rechecks_running -v
```

### 2. Flujo real: webhook firmado → SQS → worker

```bash
python -m fenix.cli send data/f02-event.json
python -m fenix.cli worker --once
```

### 3. Verificación posterior con el SDK

```bash
python - <<'PY'
import json
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.config.settings import client
from fenix.services import sqs
import os
inv = json.load(open("data/inventory.json", encoding="utf-8"))
iid = inv["node-01"]["id"]
event_id = json.load(open("data/f02-event.json", encoding="utf-8"))["event_id"]
state = client("ec2").describe_instances(InstanceIds=[iid])[
    "Reservations"][0]["Instances"][0]["State"]["Name"]
print("instance:", iid, state)
record = json.load(open("data/events.json", encoding="utf-8"))[event_id]
print("ledger F02:", json.dumps({k: v for k, v in record.items() if k != "content"}))
queue = sqs.queue_url(os.environ["QUEUE_PREFIX"])
attrs = client("sqs").get_queue_attributes(QueueUrl=queue, AttributeNames=[
    "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
print("work attrs:", json.dumps(attrs))
PY
```

## Resultado esperado

El receptor acepta el evento (202). El worker detecta `stopped`, llama a
`start_instances`, vuelve a consultar y solo entonces devuelve `repaired`. El
aviso sale, el ledger queda completo y el mensaje se confirma (ACK). La instancia
figura `running` por API y la cola queda en 0.

## Resultado obtenido

### Estado inicial

```text
instance: i-9a6ddddbc0603ac1f stopped
```

### Envío del webhook

```text
202 {"status":"accepted","event_id":"evt-f02-202611161711","message_id":"b596f8ec-4b9a-45fe-8bb3-253460ddd42a"}
```

### Worker

```text
Evento evt-f02-202611161711: instance.stopped en node-01 -> repaired
```

### Logs del worker

```text
{"timestamp": "2026-11-16T20:19:02.903010+00:00", "level": "INFO", "message": "mensaje_confirmado", "process": 14892, "thread": "MainThread", "event_id": "evt-f02-202611161711", "message_id": "b596f8ec-4b9a-45fe-8bb3-253460ddd42a", "resource_id": "node-01", "attempt": 1, "action": "instance.stopped", "status": "acknowledged"}
```

### Verificación con el SDK

```text
instance: i-9a6ddddbc0603ac1f running
ledger F02: {"attempts": 1, "repair_done": true, "repair_result": "repaired", "notified": true, "status": "done"}
work attrs: {"ApproximateNumberOfMessages": "0", "ApproximateNumberOfMessagesNotVisible": "0"}
```

### Prueba automática

```text
tests/test_i3_webhooks.py::test_repair_starts_stopped_instance_and_rechecks_running PASSED        [100%]

========================================== 1 passed in 1.08s ===========================================
```

## Qué verifica la prueba automática

- Con una instancia simulada en `stopped`, `repair` devuelve `"repaired"`.
- Se llama a `start_instances` una sola vez, con el `InstanceId` del inventario.
- Se consulta el estado **dos veces**: antes de actuar y después del `start`; el
  éxito se declara por la relectura, no por la respuesta del `start`.
- El estado final del fake es `running`.

## Criterios de aprobación

- [x] El estado inicial real era `stopped`.
- [x] `cli send` respondió 202.
- [x] Ledger: `attempts=1`, `repair_done=true`, `repair_result="repaired"`,
      `notified=true`, `status="done"`.
- [x] `describe_instances` informa `running` y la cola queda en 0.
- [x] La salida no contiene secretos.

## Observaciones

- `repair` no usa `reboot_instances`: repetir un reinicio no es convergencia.
- Si el nodo ya estuviera `running`, el resultado sería `already_ok`, no
  `repaired`; por eso el estado inicial forma parte de la evidencia.
- Un estado `pending` produce `RetryableError` (otra recepción) y
  `stopping`/`terminated`, `PermanentError`; esa clasificación está en
  `test_repair_classifies_instance_state`.
- `notify` corre en modo `console` salvo que se exporte `NOTIFY_PROVIDER`.
- Usar un `event_id` nuevo en cada corrida: reutilizarlo con otro `occurred_at`
  registra un conflicto en el ledger (F15).
