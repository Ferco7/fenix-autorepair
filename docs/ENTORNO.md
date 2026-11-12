# Entorno de trabajo — Proyecto Fénix

Guía para que cualquier integrante levante el proyecto desde cero y resuelva los
problemas típicos del laboratorio.

## 1. Versiones verificadas

| Herramienta | Versión usada | Nota |
|---|---|---|
| Python | **3.14.4** | Misma versión para todo el grupo (mínimo 3.11) |
| Docker Engine | 29.1.3 | Con permiso para el usuario |
| Docker Compose | 2.40.3 | Plugin `docker compose` |
| LocalStack | **3.8.0** | Imagen Community del Lab-1, **sin token** |
| boto3 / botocore | 1.44.1 | Ver `requirements-lock.txt` |
| FastAPI / Uvicorn | 0.162.5 / 0.54.0 | Servidor del receptor |
| pytest | 9.2.0 | Marcadores `base`, `pendiente`, `integracion` |

> El lock se genera con `pip freeze --exclude-editable`. No editar a mano.

## 2. Instalación desde cero

```bash
cd fenix
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Pegar el valor en WEBHOOK_SECRET dentro de .env
```

Verificar el entorno:

```bash
python scripts/doctor.py
```

## 3. LocalStack

```bash
docker compose up -d
docker compose ps
curl -s http://localhost:4566/_localstack/health
```

El compose fija `EC2_VM_MANAGER=mock` y habilita solo `sqs,s3,ec2`. El
`healthcheck` espera a que la API esté lista, así que `up -d` no vuelve antes de
tiempo.

Smoke real con Boto3 (crea y limpia recursos efímeros):

```bash
python scripts/check_localstack.py
```

Bajar el emulador:

```bash
docker compose down
```

No se usa volumen persistente: cada `up` arranca limpio. Volver a ejecutar
`init-queues` y `setup-demo` es parte del flujo normal.

## 4. Imagen y token

- La imagen adoptada es `localstack/localstack:3.8.0` (la del Lab-1 de la
  cátedra). **No requiere token.**
- Las imágenes `2026.03+` exigen `LOCALSTACK_AUTH_TOKEN`; sin token el contenedor
  sale con código **55** (`License activation failed`).
- Si la cátedra pide la imagen nueva, alcanza con cambiar `LOCALSTACK_IMAGE` y
  completar `LOCALSTACK_AUTH_TOKEN` en `.env`. **No se toca código.**
- No usar `:latest`: cambia sin aviso y hoy exige token.

## 5. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| Contenedor `Exited (55)` | Imagen 2026+ sin token | Volver a `3.8.0` o completar `LOCALSTACK_AUTH_TOKEN` |
| `curl: (7) Failed to connect` | El contenedor todavía arranca | `docker compose ps` y esperar `healthy`; `docker logs fenix-localstack` |
| `port is already allocated` | Otro LocalStack en 4566 | `docker ps` y bajar el contenedor anterior |
| `permission denied` al usar Docker | Usuario fuera del grupo `docker` | `sudo usermod -aG docker $USER` y volver a iniciar sesión |
| `.env` editado y “no toma” | `python-dotenv` no pisa variables exportadas | `unset VAR` o abrir una terminal nueva |
| `Falta variable AWS_DEFAULT_REGION` | Se exportó `AWS_REGION` en su lugar | Usar exactamente los nombres de `.env.example` |
| `Endpoint local inválido` | `AWS_ENDPOINT_URL` no es loopback `:4566` | Corregir a `http://localhost:4566` |
| `ModuleNotFoundError: fenix` | Paquete no instalado | `python -m pip install -e .` |
| Tests fallan por `NotImplementedError` | TODOs del equipo | Es el estado esperado hasta completar el rol |

## 6. Trampas del laboratorio

1. **`python-dotenv` no sobrescribe** variables ya exportadas. Si algo “no toma”,
   revisar `env | grep AWS_` antes de culpar al `.env`.
2. **Loopback estricto:** `settings.client()` solo acepta
   `http://localhost:4566` o `http://127.0.0.1:4566`, sin usuario ni contraseña.
3. **Un solo writer:** `data/events.json` no tiene bloqueo entre procesos. No
   correr dos workers sobre el mismo proyecto.
4. **`data/` y `logs/` son runtime:** se regeneran y están ignorados por Git.
5. **La VPC default es una decisión de laboratorio.** En producción se usaría una
   VPC propia; queda documentado en Limitaciones.
6. **El estado de LocalStack es efímero:** si se baja el contenedor, hay que
   volver a ejecutar `init-queues` y `setup-demo`.
7. **Un `receive` no es un ACK.** El mensaje sigue en la cola hasta
   `delete_message`; si el worker muere, vuelve a estar visible.

## 7. Comandos de prueba

```bash
pytest -m base -q          # apoyo del template: debe quedar verde siempre
pytest -m pendiente -q     # contratos del equipo: rojo hasta implementar
pytest -m integracion -q   # requiere LocalStack arriba
pytest -q                  # todo (incluye pendientes)
```

Con el paquete instalado no hace falta `PYTHONPATH=src`. Si se corre sin instalar:

```bash
PYTHONPATH=src pytest -m base -q
```

## 8. Flujo nominal (cuando los roles estén completos)

```bash
# Terminal 1
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli fault node-01

# Terminal 2
python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1

# Terminal 3
python -m fenix.cli worker

# Terminal 4
python -m fenix.cli send examples/node-event.json
```
