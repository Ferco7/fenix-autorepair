# F05 — Mismos datos, bytes distintos después de firmar

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

Se firma el cuerpo `{"x":1}` y se envía el mismo contenido con otro espaciado
(`{"x": 1}`). La firma corresponde a los bytes originales.

```bash
python - <<'PY'
import os, time, requests
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.utils.crypto import signature

body = b'{"x":1}'
ts = int(time.time())
hdr = f"t={ts},v1={signature(os.environ['WEBHOOK_SECRET'], ts, body)}"
r = requests.post("http://127.0.0.1:8000/webhook",
                  data=b'{"x": 1}',
                  headers={"Content-Type": "application/json",
                           "X-Webhook-Signature": hdr},
                  timeout=(2, 15))
print(r.status_code, r.text)
PY
```

## Resultado esperado

HTTP 401 y ningún mensaje nuevo en SQS.

## Resultado obtenido

```text
401 {"detail":"Firma de webhook inválida"}
```

La cola de trabajo tenía `ApproximateNumberOfMessages=0` antes y después del
envío. No se registró `MessageId` porque la petición no llegó a `send_message`.

## Qué verifica

Que el HMAC se calcula sobre los bytes crudos y no sobre una reserialización del
JSON. Cambiar solo espacios produce una firma distinta y el receptor falla
cerrado antes de decodificar el cuerpo.
