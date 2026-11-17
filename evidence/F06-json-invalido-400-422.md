# F06 — JSON roto y lista JSON firmados: 400 y 422 sin publicación

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

## Comando

```bash
python - <<'PY'
import json, os, time, requests
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.utils.crypto import signature

URL = "http://127.0.0.1:8000/webhook"
secret = os.environ["WEBHOOK_SECRET"]

def post(body):
    ts = int(time.time())
    hdr = f"t={ts},v1={signature(secret, ts, body)}"
    r = requests.post(URL, data=body,
                      headers={"Content-Type": "application/json",
                               "X-Webhook-Signature": hdr},
                      timeout=(2, 15))
    print(r.status_code, r.text)

post(b'{"schema_version":')   # JSON roto
post(b'[1,2,3]')              # JSON válido, pero no es un objeto
PY
```

## Resultado esperado

- JSON roto firmado: **400**.
- Lista JSON firmada: **422**.
- Ningún mensaje nuevo en SQS.

## Resultado obtenido

```text
400 {"detail":"JSON inválido"}
422 {"detail":"Evento no válido"}
```

La cola quedó en `ApproximateNumberOfMessages=0` antes y después de ambos
envíos.

## Qué verifica

Que la autenticación ocurre antes del parseo, que el JSON roto se distingue del
contrato inválido y que una lista JSON, aunque sea JSON válido, no se acepta
como evento. Ningún caso produce publicación.
