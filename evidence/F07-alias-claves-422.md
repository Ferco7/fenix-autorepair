# F07 — Alias ajeno y claves extra: rechazo sin cambio cloud

- **Fecha:** 2026-11-17
- **Responsable:** I3 — Mamani, Hector Mauricio (revisión de I1)
- **Rama / commit:** `fix/tandas-0-3` / commit que acompaña este archivo
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux x86_64

## Preparación

```bash
docker compose up -d
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
```

El inventario del grupo contiene solo `node-01` y `bucket-01`. No se forzó
ningún estado adicional: si el evento se hubiera publicado por error, el worker
habría actuado sobre esos dos recursos y el cambio sería visible en el SDK.

## Comando

```bash
python - <<'PY'
import json, os, time, requests
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.utils.crypto import signature

URL = "http://127.0.0.1:8000/webhook"
secret = os.environ["WEBHOOK_SECRET"]
base = {
    "schema_version": 1,
    "event_id": "evt-f07-20261117",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-11-17T12:00:00Z",
    "simulate_failures": 0,
}

def post(label, event):
    body = json.dumps(event, separators=(",", ":")).encode()
    ts = int(time.time())
    hdr = f"t={ts},v1={signature(secret, ts, body)}"
    r = requests.post(URL, data=body,
                      headers={"Content-Type": "application/json",
                               "X-Webhook-Signature": hdr},
                      timeout=(2, 15))
    print(label, r.status_code, r.text)

post("alias-ajeno", dict(base, resource_id="node-99"))
post("clave-extra", dict(base, extra="no"))
PY
```

## Resultado esperado

Ambos envíos responden **422** y no aparece ningún mensaje en SQS ni cambio en
EC2/S3.

## Resultado obtenido

```text
alias-ajeno 422 {"detail":"Evento no válido"}
clave-extra 422 {"detail":"Evento no válido"}
```

La cola quedó en `0` antes y después. Como no se publicó ningún mensaje, el
worker no se ejecutó y no hubo llamada de reparación. La instancia conservó el
estado que tenía antes de los envíos y las etiquetas del bucket no se
modificaron.

## Qué verifica

Que el esquema cerrado y la resolución por alias se aplican antes de SQS. Un
recurso que no pertenece al inventario no se puede colar como ID libre, y una
clave adicional invalida todo el evento.
