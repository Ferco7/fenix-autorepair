# F09 — Backoff 2 y 4 con `simulate_failures=2`

- **Fecha:** 2026-11-14
- **Responsable:** I2 — Maldonado, Fernando Manuel
- **Rama / commit:** `rol2-evidencias` / commit que acompaña este archivo
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux 7.0.0 x86_64

## Preparación

```bash
docker compose up -d
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
```

`inject_fault` de I6 todavía no estaba mergeado en `main`; para dejar el nodo
detenido se usó el SDK, con el mismo efecto que `python -m fenix.cli fault node-01`:

```bash
python - <<'PY'
import json, time
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.config.settings import client

inv = json.load(open("data/inventory.json", encoding="utf-8"))
iid = inv["node-01"]["id"]
ec2 = client("ec2")
ec2.stop_instances(InstanceIds=[iid])
for _ in range(20):
    r = ec2.describe_instances(InstanceIds=[iid])["Reservations"]
    state = [i["State"]["Name"] for x in r for i in x["Instances"]][0]
    if state == "stopped":
        break
    time.sleep(0.5)
print("node-01", iid, state)
PY
```

Salida real:

```text
node-01 i-99bda695003fb5be9 stopped
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
    "event_id": "evt-f09-20261114",
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
publicado: 70a95471-3732-4086-9957-0c3878e5c89a
body: {"schema_version": 1, "event_id": "evt-f09-20261114", "event_type": "instance.stopped", "resource_id": "node-01", "occurred_at": "2026-11-14T16:39:43Z", "simulate_failures": 2}
```

### Ledger después de cada intento

```text
{"content": "{...\"event_id\": \"evt-f09-20261114\"...}", "attempts": 1, "repair_done": false, "repair_result": null, "notified": false, "status": "retrying"}
{"content": "{...\"event_id\": \"evt-f09-20261114\"...}", "attempts": 2, "repair_done": false, "repair_result": null, "notified": false, "status": "retrying"}
{"content": "{...\"event_id\": \"evt-f09-20261114\"...}", "attempts": 3, "repair_done": true, "repair_result": "repaired", "notified": true, "status": "done"}
```

### Logs del worker

```text
{"timestamp": "2026-11-14T16:39:43.541260+00:00", "level": "ERROR", "message": "mensaje_reintentable", "event_id": "evt-f09-20261114", "message_id": "70a95471-3732-4086-9957-0c3878e5c89a", "resource_id": "node-01", "attempt": 1, "action": "instance.stopped", "status": "RetryableError"}
{"timestamp": "2026-11-14T16:39:46.758737+00:00", "level": "ERROR", "message": "mensaje_reintentable", "event_id": "evt-f09-20261114", "message_id": "70a95471-3732-4086-9957-0c3878e5c89a", "resource_id": "node-01", "attempt": 2, "action": "instance.stopped", "status": "RetryableError"}
{"timestamp": "2026-11-14T16:39:52.030779+00:00", "level": "INFO", "message": "mensaje_confirmado", "event_id": "evt-f09-20261114", "message_id": "70a95471-3732-4086-9957-0c3878e5c89a", "resource_id": "node-01", "attempt": 3, "action": "instance.stopped", "status": "ok"}
```

Las diferencias entre intentos son 3,2 s y 5,3 s; incluyen el arranque de cada
proceso CLI. La visibilidad aplicada por `retry_later` fue de 2 s y 4 s, según
`min(30, 2 ** ApproximateReceiveCount)`.

### Verificación con el SDK

```text
instance: i-99bda695003fb5be9 running
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
- `notify` se ejecutó en modo `console` (default local); no se envió nada a
  Telegram para esta prueba.
- El nodo quedó en `running` verificado por `describe_instances`, no solo por el
  log del worker.
