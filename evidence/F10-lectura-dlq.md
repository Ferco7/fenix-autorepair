# F10 — Falla persistente y lectura real de la DLQ

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

Se usaron colas propias (`fenix-i2dlq-20261114`) para no contaminar las colas del
grupo y para poder borrarlas después de documentar la DLQ.

## Comando

### 1. Crear las colas y publicar el evento persistente

```bash
python - <<'PY'
import json, os, time
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.services import sqs

prefix = "fenix-i2dlq-20261114"
work, dead = sqs.ensure_queues(prefix)
client = sqs.client("sqs")
for name, url in (("work", work), ("dlq", dead)):
    attrs = client.get_queue_attributes(QueueUrl=url,
                                        AttributeNames=["All"])["Attributes"]
    print(name, url)
    print("  RedrivePolicy:", attrs.get("RedrivePolicy"))
    print("  VisibilityTimeout:", attrs.get("VisibilityTimeout"))
    print("  MessageRetentionPeriod:", attrs.get("MessageRetentionPeriod"))
event = {
    "schema_version": 1,
    "event_id": "evt-f10-20261114",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "simulate_failures": 5,
}
r = client.send_message(QueueUrl=work, MessageBody=json.dumps(event))
print("publicado:", r["MessageId"])
print("body:", json.dumps(event))
PY
```

### 2. Consumir hasta agotar `maxReceiveCount`

```bash
export QUEUE_PREFIX=fenix-i2dlq-20261114
python -m fenix.cli worker --once
sleep 3
python -m fenix.cli worker --once
sleep 5
python -m fenix.cli worker --once
sleep 9
python -m fenix.cli worker --once   # esta recepción dispara el redrive
```

### 3. Leer la DLQ (sin borrar el mensaje)

```bash
python - <<'PY'
import json
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.services import sqs

client = sqs.client("sqs")
dead = client.get_queue_url(QueueName="fenix-i2dlq-20261114-dlq")["QueueUrl"]
work = client.get_queue_url(QueueName="fenix-i2dlq-20261114-events")["QueueUrl"]
msg = client.receive_message(QueueUrl=dead, MaxNumberOfMessages=1,
                             WaitTimeSeconds=2,
                             AttributeNames=["All"])["Messages"][0]
print("MessageId:", msg["MessageId"])
print("Body:", msg["Body"])
print("Attributes:", json.dumps(msg.get("Attributes", {}), indent=2))
print("ReceiptHandle:", msg["ReceiptHandle"][:20] + "...")
wa = client.get_queue_attributes(QueueUrl=work,
    AttributeNames=["ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
print("work attrs:", json.dumps(wa))
PY
```

## Resultado esperado

El mensaje no se confirma: tras tres recepciones fallidas, SQS lo deriva a la
DLQ con `maxReceiveCount=3`. El Body original debe conservarse.

## Resultado obtenido

### Colas y publicación

```text
work http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-i2dlq-20261114-events
  RedrivePolicy: {"deadLetterTargetArn": "arn:aws:sqs:us-east-1:000000000000:fenix-i2dlq-20261114-dlq", "maxReceiveCount": 3}
  VisibilityTimeout: 45
  MessageRetentionPeriod: 345600
dlq http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-i2dlq-20261114-dlq
  RedrivePolicy: None
  VisibilityTimeout: 30
  MessageRetentionPeriod: 1209600
publicado: 1585046c-2390-4d73-b4fc-a2063a85733e
body: {"schema_version": 1, "event_id": "evt-f10-20261114", "event_type": "instance.stopped", "resource_id": "node-01", "occurred_at": "2026-11-14T16:40:08Z", "simulate_failures": 5}
```

### Ledger después de cada intento

```text
{"content": "{...\"event_id\": \"evt-f10-20261114\"...}", "attempts": 1, "repair_done": false, "repair_result": null, "notified": false, "status": "retrying"}
{"content": "{...\"event_id\": \"evt-f10-20261114\"...}", "attempts": 2, "repair_done": false, "repair_result": null, "notified": false, "status": "retrying"}
{"content": "{...\"event_id\": \"evt-f10-20261114\"...}", "attempts": 3, "repair_done": false, "repair_result": null, "notified": false, "status": "retrying"}
```

### Logs del worker

```text
{"timestamp": "2026-11-14T16:40:14.228324+00:00", "level": "ERROR", "message": "mensaje_reintentable", "event_id": "evt-f10-20261114", "message_id": "1585046c-2390-4d73-b4fc-a2063a85733e", "resource_id": "node-01", "attempt": 1, "action": "instance.stopped", "status": "RetryableError"}
{"timestamp": "2026-11-14T16:40:17.471321+00:00", "level": "ERROR", "message": "mensaje_reintentable", "event_id": "evt-f10-20261114", "message_id": "1585046c-2390-4d73-b4fc-a2063a85733e", "resource_id": "node-01", "attempt": 2, "action": "instance.stopped", "status": "RetryableError"}
{"timestamp": "2026-11-14T16:40:22.712007+00:00", "level": "ERROR", "message": "mensaje_reintentable", "event_id": "evt-f10-20261114", "message_id": "1585046c-2390-4d73-b4fc-a2063a85733e", "resource_id": "node-01", "attempt": 3, "action": "instance.stopped", "status": "RetryableError"}
```

### Lectura real de la DLQ

```text
poll DLQ 1: 1 mensaje(s)
MessageId: 1585046c-2390-4d73-b4fc-a2063a85733e
Body: {"schema_version": 1, "event_id": "evt-f10-20261114", "event_type": "instance.stopped", "resource_id": "node-01", "occurred_at": "2026-11-14T16:40:08Z", "simulate_failures": 5}
Attributes: {
  "SenderId": "000000000000",
  "SentTimestamp": "1794674408579",
  "ApproximateReceiveCount": "4",
  "DeadLetterQueueSourceArn": "arn:aws:sqs:us-east-1:000000000000:fenix-i2dlq-20261114-events",
  "ApproximateFirstReceiveTimestamp": "1794674439089"
}
ReceiptHandle: NjFmMzNjOTMtMWU0NS00...
work attrs: {"ApproximateNumberOfMessages": "0", "ApproximateNumberOfMessagesNotVisible": "0"}
```

El `Body` en la DLQ es idéntico al publicado. `ApproximateReceiveCount=4`
corresponde a tres entregas fallidas más la recepción de lectura en la DLQ;
`DeadLetterQueueSourceArn` identifica la cola de origen y la cola de trabajo
quedó en 0 mensajes.

### Limpieza posterior (después de documentar)

```bash
python - <<'PY'
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.services import sqs
client = sqs.client("sqs")
for name in ("fenix-i2dlq-20261114-events", "fenix-i2dlq-20261114-dlq"):
    client.delete_queue(QueueUrl=client.get_queue_url(QueueName=name)["QueueUrl"])
    print("cola eliminada:", name)
PY
```

```text
cola eliminada: fenix-i2dlq-20261114-events
cola eliminada: fenix-i2dlq-20261114-dlq
```

## Evidencia

- Salida real transcripta arriba; el mensaje se leyó y documentó antes de borrar
  las colas.
- Logs de runtime: `logs/fenix-worker-<pid>.jsonl` (gitignored, no se versionan).

## Observaciones

- `maxReceiveCount=3` lo impone `ensure_queues` con `RedrivePolicy`; el redrive
  se materializa en la recepción siguiente, no en un cronómetro exacto.
- No se hizo ACK en ningún intento: el mensaje seguía existiendo en la DLQ.
- `ApproximateReceiveCount` y los contadores de SQS son aproximados; la
  evidencia principal es el `Body` original leído desde la DLQ.
- No se usaron las colas del grupo para no dejar mensajes venenosos en el
  laboratorio compartido.
