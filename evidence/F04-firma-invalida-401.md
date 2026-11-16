# F04 — Firma ausente, alterada o con timestamp viejo: 401 y sin publicación

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
```

Receptor en otra terminal (un solo worker de Uvicorn):

```bash
python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
```

## Comando

### 1. Pruebas automáticas (sin LocalStack)

```bash
pytest tests/test_i3_webhooks.py -k "invalid_signature or strict_t_and_v1 or only_after_authentication" -v
```

### 2. Corrida real contra el receptor

Envía el mismo cuerpo con tres firmas inválidas y compara la cola antes y
después. No imprime el secreto ni la cabecera completa.

```bash
python - <<'PY'
import json, os, time
import requests
from dotenv import load_dotenv
load_dotenv(".env")
from fenix.config.settings import client
from fenix.services import sqs
from fenix.utils.crypto import signature

URL = "http://127.0.0.1:8000/webhook"
secret = os.environ["WEBHOOK_SECRET"]
queue = sqs.queue_url(os.environ["QUEUE_PREFIX"])
sqsc = client("sqs")

def pending():
    attrs = sqsc.get_queue_attributes(QueueUrl=queue, AttributeNames=[
        "ApproximateNumberOfMessages",
        "ApproximateNumberOfMessagesNotVisible",
        "ApproximateNumberOfMessagesDelayed"])["Attributes"]
    return json.dumps(attrs)

def post(label, headers):
    r = requests.post(URL, data=body, timeout=(2, 10),
                      headers={"Content-Type": "application/json", **headers})
    print(f"{label}: HTTP {r.status_code} {r.text}")

now = int(time.time())
event = {"schema_version": 1, "event_id": "evt-f04-" + time.strftime("%Y%m%d%H%M"),
         "event_type": "instance.stopped", "resource_id": "node-01",
         "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "simulate_failures": 0}
body = json.dumps(event).encode("utf-8")

valid = signature(secret, now, body)
tampered = valid[:-1] + ("0" if valid[-1] != "0" else "1")  # un solo hex distinto
old = now - 600  # fuera de la ventana de 300 s, pero con firma correcta para ese t
old_valid = signature(secret, old, body)

print("cola antes:  ", pending())
post("1 firma ausente        ", {})
post("2 firma alterada       ", {"X-Webhook-Signature": f"t={now},v1={tampered}"})
post("3 timestamp viejo -600s", {"X-Webhook-Signature": f"t={old},v1={old_valid}"})
print("cola después:", pending())
PY
```

## Resultado esperado

Los tres envíos responden **401** con el mismo detalle genérico
(`Firma de webhook inválida`), sin distinguir si falló el formato, el reloj o el
digest. Los contadores de la cola no cambian entre "antes" y "después": no se
publicó ningún mensaje.

## Resultado obtenido

### Pruebas automáticas

```text
========================================= test session starts ==========================================
platform win32 -- Python 3.14.4, pytest-9.2.0, pluggy-1.7.0 -- 
..\fenix-autorepair\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: ..\fenix-autorepair
configfile: pyproject.toml
plugins: anyio-4.16.0
collected 11 items / 6 deselected / 5 selected                                                          

tests/test_i3_webhooks.py::test_webhook_rejects_invalid_signature_without_publishing PASSED       [ 20%]
tests/test_i3_webhooks.py::test_verify_requires_one_strict_t_and_v1[t=1000,t=1000,v1=0000000000000000000000000000000000000000000000000000000000000000] PASSED [ 40%]
tests/test_i3_webhooks.py::test_verify_requires_one_strict_t_and_v1[t=1000,v1=000000000000000000000000000000000000000000000000000000000000000] PASSED [ 60%]
tests/test_i3_webhooks.py::test_verify_requires_one_strict_t_and_v1[t=abc,v1=0000000000000000000000000000000000000000000000000000000000000000] PASSED [ 80%]
tests/test_i3_webhooks.py::test_webhook_parses_json_only_after_authentication PASSED              [100%]

=================================== 5 passed, 6 deselected in 1.02s ====================================
```

### Corrida real

```text
cola antes:   {"ApproximateNumberOfMessages": "0", "ApproximateNumberOfMessagesNotVisible": "0", "ApproximateNumberOfMessagesDelayed": "0"}
1 firma ausente        : HTTP 401 {"detail":"Firma de webhook inválida"}
2 firma alterada       : HTTP 401 {"detail":"Firma de webhook inválida"}
3 timestamp viejo -600s: HTTP 401 {"detail":"Firma de webhook inválida"}
cola después: {"ApproximateNumberOfMessages": "0", "ApproximateNumberOfMessagesNotVisible": "0", "ApproximateNumberOfMessagesDelayed": "0"}
```

### Log de acceso del receptor

```text
INFO:     127.0.0.1:63455 - "POST /webhook HTTP/1.1" 401 Unauthorized
INFO:     127.0.0.1:63456 - "POST /webhook HTTP/1.1" 401 Unauthorized
INFO:     127.0.0.1:63457 - "POST /webhook HTTP/1.1" 401 Unauthorized
```

## Qué verifica cada prueba

- `test_webhook_rejects_invalid_signature_without_publishing`: una firma
  `t=1,v1=000…0` devuelve 401 con `detail == "Firma de webhook inválida"` y la
  lista de publicaciones queda vacía.
- `test_verify_requires_one_strict_t_and_v1` (3 casos): `verify` rechaza `t`
  duplicado, `v1` de 63 caracteres y `t` no numérico, siempre con el mismo
  mensaje.
- `test_webhook_parses_json_only_after_authentication`: un cuerpo sin firma es
  401 aunque además sea JSON roto; el parseo ocurre solo con firma válida.

## Criterios de aprobación

- [x] Las tres respuestas reales son 401 con el mismo `detail`.
- [x] Los contadores de la cola son idénticos antes y después.
- [x] Las pruebas automáticas pasan.
- [x] La salida no contiene `WEBHOOK_SECRET` ni la cabecera completa.

## Observaciones

- El control positivo (firma válida → 202 con `event_id` y `message_id`) está
  cubierto por `test_webhook_returns_202_only_after_sqs_message_id` y por los
  `cli send` de F02 y F03. No se repite acá para no dejar un mensaje en la cola
  que luego consumiría el worker de esas pruebas.
- La firma del caso 3 es correcta para su propio `t`: lo que se rechaza es la
  antigüedad (`abs(now - t) > 300`), no el digest.
- Si falta `WEBHOOK_SECRET` en el entorno del receptor, también se responde 401
  (falla cerrada). Si los tres casos dan 401 pero el control de F02 también,
  revisar que el secreto del receptor y el de la CLI sean el mismo.
- La ventana HMAC no impide repetir un evento válido dentro de los 300 s; eso lo
  cubre `event_id` + ledger (F11).
