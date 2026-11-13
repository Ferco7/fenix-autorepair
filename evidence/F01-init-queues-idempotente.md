# F01 — init-queues / setup-demo idempotente

- **Fecha:** 2026-11-13
- **Responsable:** I2 — Maldonado, Fernando Manuel
- **Rama / commit:** `rol2-mensajeria` / commit que acompaña este archivo
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux x86_64

## Preparación

```bash
docker compose down
docker compose up -d
python scripts/doctor.py
```

Resultado del doctor: **11 OK, 0 avisos, 0 fallos**.

LocalStack se levantó desde cero para esta corrida: el contenedor se eliminó y
se volvió a crear sin volumen persistente. El `data/inventory.json` anterior
quedó obsoleto y `setup-demo` lo reconcilió con los IDs nuevos del emulador.

## Comando

```bash
python -m fenix.cli init-queues
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli setup-demo
```

## Resultado esperado

Mismas URLs de cola, mismos IDs de inventario y ningún recurso duplicado entre
la primera y la segunda corrida. `node-01` debe guardar `security_group_id` y
`expected_tags`; `bucket-01`, `expected_tags`.

## Resultado obtenido

### init-queues — corrida 1

```text
('http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-grupo01-events', 'http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-grupo01-dlq')
```

### init-queues — corrida 2

```text
('http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-grupo01-events', 'http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-grupo01-dlq')
```

Las dos corridas devolvieron exactamente las mismas URLs, en el mismo orden
(cola de trabajo primero, DLQ después).

### setup-demo — corrida 1

```text
{'_lab': {'group': 'grupo01', 'region': 'us-east-1', 'vpc_id': 'vpc-390a7fc7', 'image_id': 'ami-0002eba4f029226a3', 'security_group_id': 'sg-b9380eca7bc9f4cc3', 'security_group_name': 'fenix-grupo01-sg', 'instance_name': 'fenix-grupo01-node', 'bucket_name': 'fenix-grupo01-demo'}, 'node-01': {'type': 'ec2', 'id': 'i-148d6b01c3c367ecb', 'security_group_id': 'sg-b9380eca7bc9f4cc3', 'expected_tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}}, 'bucket-01': {'type': 's3', 'id': 'fenix-grupo01-demo', 'expected_tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}}}
```

### setup-demo — corrida 2

```text
{'_lab': {'group': 'grupo01', 'region': 'us-east-1', 'vpc_id': 'vpc-390a7fc7', 'image_id': 'ami-0002eba4f029226a3', 'security_group_id': 'sg-b9380eca7bc9f4cc3', 'security_group_name': 'fenix-grupo01-sg', 'instance_name': 'fenix-grupo01-node', 'bucket_name': 'fenix-grupo01-demo'}, 'node-01': {'type': 'ec2', 'id': 'i-148d6b01c3c367ecb', 'security_group_id': 'sg-b9380eca7bc9f4cc3', 'expected_tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}}, 'bucket-01': {'type': 's3', 'id': 'fenix-grupo01-demo', 'expected_tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}}}
```

La segunda corrida devolvió el mismo inventario: mismo `security_group_id`,
mismo `InstanceId` (`i-148d6b01c3c367ecb`) y mismo bucket
(`fenix-grupo01-demo`).

### data/inventory.json (runtime, no versionado)

```json
{
  "_lab": {
    "group": "grupo01",
    "region": "us-east-1",
    "vpc_id": "vpc-390a7fc7",
    "image_id": "ami-0002eba4f029226a3",
    "security_group_id": "sg-b9380eca7bc9f4cc3",
    "security_group_name": "fenix-grupo01-sg",
    "instance_name": "fenix-grupo01-node",
    "bucket_name": "fenix-grupo01-demo"
  },
  "node-01": {
    "type": "ec2",
    "id": "i-148d6b01c3c367ecb",
    "security_group_id": "sg-b9380eca7bc9f4cc3",
    "expected_tags": {
      "ManagedBy": "ppa2",
      "Project": "fenix",
      "GroupId": "grupo01",
      "Owner": "grupo01"
    }
  },
  "bucket-01": {
    "type": "s3",
    "id": "fenix-grupo01-demo",
    "expected_tags": {
      "ManagedBy": "ppa2",
      "Project": "fenix",
      "GroupId": "grupo01",
      "Owner": "grupo01"
    }
  }
}
```

## Verificación con el SDK

Lectura posterior a la corrida, sin crear ni modificar recursos:

```text
work_url: http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-grupo01-events
dlq_url: http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/fenix-grupo01-dlq
events: arn=arn:aws:sqs:us-east-1:000000000000:fenix-grupo01-events
  VisibilityTimeout: 45
  MessageRetentionPeriod: 345600
  RedrivePolicy: {"deadLetterTargetArn": "arn:aws:sqs:us-east-1:000000000000:fenix-grupo01-dlq", "maxReceiveCount": 3}
dlq: arn=arn:aws:sqs:us-east-1:000000000000:fenix-grupo01-dlq
  VisibilityTimeout: 30
  MessageRetentionPeriod: 1209600
instance: i-148d6b01c3c367ecb running t3.micro
instance_sg: sg-b9380eca7bc9f4cc3
instance_tags: {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01', 'Name': 'fenix-grupo01-node'}
bucket: fenix-grupo01-demo
bucket_tags: {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}
instancias grupo01: 1 ['i-148d6b01c3c367ecb']
buckets: ['fenix-grupo01-demo']
```

## Evidencia

- La salida real está transcripta arriba; no se adjunta captura de pantalla.
- Logs de runtime: `logs/fenix-init-queues-<pid>.jsonl` y
  `logs/fenix-setup-demo-<pid>.jsonl` (gitignored, no se versionan).

## Observaciones

- `init-queues` fuerza la `RedrivePolicy` con `set_queue_attributes` y devuelve
  las URLs del SDK; no arma URLs a mano.
- `setup_demo` reutilizó la instancia, el security group y el bucket de la
  primera corrida por tags y `ClientToken`; no creó duplicados.
- Contrato del inventario alineado con el §3.3 del TP: `node-01` guarda
  `security_group_id` y `expected_tags`; `bucket-01` guarda `expected_tags`.
  Las `expected_tags` son solo las cuatro obligatorias (`ManagedBy`, `Project`,
  `GroupId`, `Owner`); la instancia conserva además su `Name` real, que no forma
  parte de la política a restaurar.
- La clave reservada `_lab` conserva metadatos del laboratorio y el SG como
  punto de control de una creación interrumpida. Los aliases `node-01` y
  `bucket-01` son los únicos recursos autorizados del inventario.
- `data/inventory.json` es estado de runtime y está en `.gitignore`.
- **Pendiente de I2 para completar el §3.2.2:** leer un mensaje real de la DLQ
  sin eliminarlo antes de documentarlo. Requiere que I6 produzca el redrive con
  un evento inválido o con `simulate_failures=5`; se documentará en F10.
- F09 y F10 quedan pendientes de I3 (`repair`) e I4 (`notify`); el worker de
  I5 ya está mergeado en `main`.
