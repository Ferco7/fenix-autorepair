# F03 — Bucket sin tag Owner → etiquetas restauradas y ajenas preservadas

- **Fecha:** 16-11-2026
- **Responsable:** I3 — Mamani, Hector Mauricio
- **Rama / commit:** `main` = `a30b45b`
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3

## Preparación

```bash
docker compose up -d
python scripts/doctor.py
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
```

Se agrega una etiqueta ajena (`Ambiente=laboratorio`) para comprobar que la
reparación no la borra, y después se quita `Owner` con la inyección de fallas:

```bash
python - <<'PY'
import json
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.config.settings import client
inv = json.load(open("data/inventory.json", encoding="utf-8"))
bucket = inv["bucket-01"]["id"]
s3 = client("s3")
tags = {t["Key"]: t["Value"] for t in s3.get_bucket_tagging(Bucket=bucket)["TagSet"]}
tags["Ambiente"] = "laboratorio"
s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [
    {"Key": k, "Value": v} for k, v in tags.items()]})
PY
python -m fenix.cli fault bucket-01
```

Etiquetas iniciales leídas con el SDK (no debe aparecer `Owner`):

```bash
python - <<'PY'
import json
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.config.settings import client
inv = json.load(open("data/inventory.json", encoding="utf-8"))
bucket = inv["bucket-01"]["id"]
tags = {t["Key"]: t["Value"] for t in client("s3").get_bucket_tagging(
    Bucket=bucket)["TagSet"]}
print("bucket:", bucket)
print("tags:", json.dumps(tags, sort_keys=True))
PY
```

Evento nuevo con `event_id` único:

```bash
python - <<'PY'
import json, time
event = {"schema_version": 1, "event_id": "evt-f03-" + time.strftime("%Y%m%d%H%M"),
         "event_type": "bucket.tags_missing", "resource_id": "bucket-01",
         "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "simulate_failures": 0}
json.dump(event, open("data/f03-event.json", "w", encoding="utf-8"), indent=2)
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
pytest tests/test_i3_webhooks.py::test_repair_merges_tags_and_verifies_s3_result -v
```

### 2. Flujo real: webhook firmado → SQS → worker

```bash
python -m fenix.cli send data/f03-event.json
python -m fenix.cli worker --once
```

### 3. Verificación posterior con el SDK

```bash
python - <<'PY'
import json, os
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.config.settings import client
from fenix.services import sqs
inv = json.load(open("data/inventory.json", encoding="utf-8"))
bucket = inv["bucket-01"]["id"]
event_id = json.load(open("data/f03-event.json", encoding="utf-8"))["event_id"]
tags = {t["Key"]: t["Value"] for t in client("s3").get_bucket_tagging(
    Bucket=bucket)["TagSet"]}
print("bucket:", bucket)
print("tags:", json.dumps(tags, sort_keys=True))
record = json.load(open("data/events.json", encoding="utf-8"))[event_id]
print("ledger F03:", json.dumps({k: v for k, v in record.items() if k != "content"}))
queue = sqs.queue_url(os.environ["QUEUE_PREFIX"])
attrs = client("sqs").get_queue_attributes(QueueUrl=queue, AttributeNames=[
    "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
print("work attrs:", json.dumps(attrs))
PY
```

## Resultado esperado

El worker lee las etiquetas actuales, combina las cuatro obligatorias del
inventario (`ManagedBy`, `Project`, `GroupId`, `Owner`) sin tocar las ajenas,
escribe una vez y vuelve a leer para verificar. El bucket termina con las cuatro
obligatorias más `Ambiente=laboratorio`, el ledger queda completo y la cola en 0.

## Resultado obtenido

### Etiquetas iniciales

```text
bucket: fenix-grupo01-demo
tags: {"Ambiente": "laboratorio", "GroupId": "grupo01", "ManagedBy": "ppa2", "Project": "fenix"}
```

### Envío del webhook

```text
202 {"status":"accepted","event_id":"evt-f03-202611161738","message_id":"6dd56754-8184-4acb-af52-f5b166e30a44"}
```

### Worker

```text
Evento evt-f03-202611161738: bucket.tags_missing en bucket-01 -> repaired
```

### Logs del worker

```text
{"timestamp": "2026-11-16T20:40:20.208975+00:00", "level": "INFO", "message": "mensaje_confirmado", "process": 14584, "thread": "MainThread", "event_id": "evt-f03-202611161738", "message_id": "6dd56754-8184-4acb-af52-f5b166e30a44", "resource_id": "bucket-01", "attempt": 1, "action": "bucket.tags_missing", "status": "acknowledged"}
```

### Verificación con el SDK

```text
tags: {"Ambiente": "laboratorio", "GroupId": "grupo01", "ManagedBy": "ppa2", "Owner": "grupo01", "Project": "fenix"}
ledger F03: {"attempts": 1, "repair_done": true, "repair_result": "repaired", "notified": true, "status": "done"}
work attrs: {"ApproximateNumberOfMessages": "0", "ApproximateNumberOfMessagesNotVisible": "0"}
```

### Prueba automática

```text
tests/test_i3_webhooks.py::test_repair_merges_tags_and_verifies_s3_result PASSED                  [100%]

========================================== 1 passed in 1.03s ===========================================
```

## Qué verifica la prueba automática

- Parte de un bucket simulado con `Foreign=keep` y `ManagedBy=ppa2`.
- `repair` devuelve `"repaired"` y el resultado final es
  `{Foreign, ManagedBy, Owner}`: agrega la faltante y conserva la ajena.
- Hay una sola escritura (`put_bucket_tagging`) y dos lecturas: la previa y la
  de verificación.

## Criterios de aprobación

- [x] Antes: sin `Owner` y con `Ambiente=laboratorio`.
- [x] `cli send` respondió 202.
- [x] Después: las cuatro obligatorias presentes y `Ambiente=laboratorio` intacta.
- [x] Ledger: `attempts=1`, `repair_done=true`, `repair_result="repaired"`,
      `notified=true`, `status="done"`.
- [x] La cola queda en 0 y la salida no contiene secretos.

## Observaciones

- `put_bucket_tagging` reemplaza el conjunto completo de etiquetas; por eso
  `repair` combina `{**actuales, **obligatorias}` antes de escribir.
- Un bucket sin etiquetas se trata como conjunto vacío solo ante `NoSuchTagSet`;
  cualquier otro error se clasifica como reintentable o permanente.
- `inject_fault("bucket-01")` exige que el bucket ya tenga `ManagedBy`, `Project`
  y `GroupId` del grupo; si no los tiene, falla con `PermanentError` sin escribir.
- La etiqueta `Ambiente` se agrega a mano solo para esta evidencia; no forma
  parte de la política del inventario.
- Usar un `event_id` nuevo en cada corrida (ver F15 para el caso de reutilización).
