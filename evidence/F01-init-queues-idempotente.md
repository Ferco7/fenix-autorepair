# F01 — init-queues / setup-demo idempotente

- **Fecha:** 2026-11-12
- **Responsable:** I2 — Maldonado, Fernando Manuel
- **Rama / commit:** `rol2-mensajeria` / `ab45ecf` (merge de `main` con el aporte de I1)
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux x86_64

## Preparación

```bash
docker compose up -d
python scripts/doctor.py
```

Resultado del doctor: **11 OK, 0 avisos, 0 fallos**.

LocalStack se levantó desde cero para esta corrida. El estado anterior del
emulador no se reutilizó.

## Comando

```bash
python -m fenix.cli init-queues
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli setup-demo
```

## Resultado esperado

Mismas URLs de cola, mismos IDs de inventario y ningún recurso duplicado entre
la primera y la segunda corrida.

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
{'_lab': {'group': 'grupo01', 'region': 'us-east-1', 'vpc_id': 'vpc-020f665c', 'image_id': 'ami-0002eba4f029226a3', 'security_group_id': 'sg-160def24e2eeb93bb', 'security_group_name': 'fenix-grupo01-sg', 'instance_name': 'fenix-grupo01-node', 'bucket_name': 'fenix-grupo01-demo'}, 'node-01': {'type': 'ec2', 'id': 'i-39a35ab3353103463', 'tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01', 'Name': 'fenix-grupo01-node'}}, 'bucket-01': {'type': 's3', 'id': 'fenix-grupo01-demo', 'tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}}}
```

### setup-demo — corrida 2

```text
{'_lab': {'group': 'grupo01', 'region': 'us-east-1', 'vpc_id': 'vpc-020f665c', 'image_id': 'ami-0002eba4f029226a3', 'security_group_id': 'sg-160def24e2eeb93bb', 'security_group_name': 'fenix-grupo01-sg', 'instance_name': 'fenix-grupo01-node', 'bucket_name': 'fenix-grupo01-demo'}, 'node-01': {'type': 'ec2', 'id': 'i-39a35ab3353103463', 'tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01', 'Name': 'fenix-grupo01-node'}}, 'bucket-01': {'type': 's3', 'id': 'fenix-grupo01-demo', 'tags': {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}}}
```

La segunda corrida devolvió el mismo inventario: mismo `security_group_id`,
mismo `InstanceId` (`i-39a35ab3353103463`) y mismo bucket
(`fenix-grupo01-demo`).

### data/inventory.json (runtime, no versionado)

```json
{
  "_lab": {
    "group": "grupo01",
    "region": "us-east-1",
    "vpc_id": "vpc-020f665c",
    "image_id": "ami-0002eba4f029226a3",
    "security_group_id": "sg-160def24e2eeb93bb",
    "security_group_name": "fenix-grupo01-sg",
    "instance_name": "fenix-grupo01-node",
    "bucket_name": "fenix-grupo01-demo"
  },
  "node-01": {
    "type": "ec2",
    "id": "i-39a35ab3353103463",
    "tags": {
      "ManagedBy": "ppa2",
      "Project": "fenix",
      "GroupId": "grupo01",
      "Owner": "grupo01",
      "Name": "fenix-grupo01-node"
    }
  },
  "bucket-01": {
    "type": "s3",
    "id": "fenix-grupo01-demo",
    "tags": {
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
events: arn:aws:sqs:us-east-1:000000000000:fenix-grupo01-events
  VisibilityTimeout: 45
  MessageRetentionPeriod: 345600
  RedrivePolicy: {"deadLetterTargetArn": "arn:aws:sqs:us-east-1:000000000000:fenix-grupo01-dlq", "maxReceiveCount": 3}
dlq: arn:aws:sqs:us-east-1:000000000000:fenix-grupo01-dlq retencion: 1209600
instance: i-39a35ab3353103463 running type: t3.micro
  tags: {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01', 'Name': 'fenix-grupo01-node'}
bucket: fenix-grupo01-demo
  tags: {'ManagedBy': 'ppa2', 'Project': 'fenix', 'GroupId': 'grupo01', 'Owner': 'grupo01'}
instancias totales: 1
buckets: ['fenix-grupo01-demo']
```

## Evidencia

- La salida real está transcripta arriba; no se adjunta captura de pantalla.
- Logs de runtime: `logs/fenix-init-queues-<pid>.jsonl` y
  `logs/fenix-setup-demo-<pid>.jsonl` (gitignored, no se versionan).

## Observaciones

- `init-queues` fuerza la `RedrivePolicy` con `set_queue_attributes` y devuelve
  las URLs del SDK; no arma URLs a mano.
- `setup-demo` reutilizó la instancia, el security group y el bucket de la
  primera corrida por tags y `ClientToken`; no creó duplicados.
- La clave reservada `_lab` guarda metadatos del laboratorio. Los aliases
  `node-01` y `bucket-01` son los únicos recursos autorizados del inventario.
- `data/inventory.json` es estado de runtime y está en `.gitignore`.
- F09 y F10 quedan pendientes de I3 (`repair`) e I4 (`notify`); el worker de
  I5 ya está mergeado en `main`.
