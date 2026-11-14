# TP Final 1 - Sistema de Autorreparación de Infraestructura (Proyecto Fénix)

Sistema que recibe una alerta de laboratorio mediante un **webhook autenticado**, la guarda en **SQS**, repara un recurso emulado por **Boto3/LocalStack** y comunica el resultado a **Telegram o Slack**.

> Estado: **base endurecida** sobre la plantilla de Fénix. Las 14 funciones de negocio siguen pendientes y se reparten por rol (ver [`docs/ROLES.md`](docs/ROLES.md)). Completar TODOs, pruebas y evidencias antes de la entrega.

## 1. Objetivo del sistema

Integrar lo trabajado en Tritón y Vulcano con dos reparaciones pequeñas y verificables:
1. Una instancia **EC2 mock** detenida vuelve a `running`.
2. Un bucket **S3** recupera las **etiquetas obligatorias**.

Flujo: `POST /webhook` (HMAC, raw bytes) → validación + publicación en SQS (202) → worker consume → repara y verifica por API → notifica → confirma (ACK/delete) solo tras éxito durable. Mensajes fallidos se reintentan y van a **DLQ** si persiste la falla. Repetir el mismo evento o reiniciar el worker **no repite acciones ya verificadas** (idempotencia por `event_id` + ledger).

## 2. Integrantes y roles

| Rol | Apellido y nombre | Correo | Módulos principales | Pruebas defendidas |
|---|---|---|---|---|
| I1 - Entradas y Excepciones | Herrera, Nancy Mariel | _Completar_ | `src/fenix/utils/validation.py`, `src/fenix/utils/errors.py`, `src/fenix/services/events.py` | _Completar_ |
| I2 - Mensajería e Inventario Cloud | Maldonado, Fernando Manuel | bynanofer@gmail.com | `src/fenix/services/sqs.py`, `src/fenix/services/demo.py` | `tests/test_i2_mensajeria.py` (9: 7 unitarios + 2 de integración) + `tests/test_scenarios.py::test_redrive_with_localstack` (custodia I6) |
| I3 - Webhooks y Reparación | Mamani, Hector Mauricio | maurobvx@gmail.com | `src/fenix/utils/crypto.py`, `src/fenix/services/receiver.py`, `src/fenix/services/remediation.py` (`repair`) | `tests/test_i3_webhooks.py` (11 casos) |
| I4 - Observabilidad y Comunicación | Alegre, Facundo Sebastián | _Completar_ | `src/fenix/utils/logging_json.py`, `src/fenix/services/notifications.py` | _Completar_ |
| I5 - Integración y Worker | Rodríguez, Hector Fernando | elferchurodriguez08@gmail.com | `src/fenix/services/worker.py`, `src/fenix/services/remediation.py` (`handle`), `src/fenix/cli.py` | `tests/test_i5_worker.py` (13 casos) |
| I6 - Pruebas y Diagnóstico | Gaspar, Lautaro Miguel Angel | lautaro.lg48@gmail.com | `tests/`, `src/fenix/services/demo.py` (`inject_fault`) | _Completar_ |

> **Nota**: el correo es obligatorio en la entrega. Cada estudiante debe poder explicar y modificar su código, realizar commits propios y revisar al menos un módulo de otro compañero. La asignación operativa está en [`docs/ROLES.md`](docs/ROLES.md).

## 3. Prerrequisitos y versiones

- Python **3.14.4** (misma versión para todo el grupo; mínimo admitido 3.11)
- Docker Engine 29+ y Docker Compose 2.40+
- LocalStack **3.8.0** (imagen Community del Lab-1, **sin token**) con `sqs,s3,ec2` y `EC2_VM_MANAGER=mock`
- Dependencias: `boto3`, `fastapi`, `uvicorn`, `requests`, `python-dotenv`, `pytest`, `httpx` (versiones exactas en `requirements-lock.txt`)
- Guía de instalación y problemas frecuentes: [`docs/ENTORNO.md`](docs/ENTORNO.md)

## 4. Instalación desde cero

```bash
# 1) Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1

# 2) Instalar el paquete en modo editable
python -m pip install --upgrade pip
python -m pip install -e .

# 3) Configurar variables de entorno (sin valores privados)
cp .env.example .env
# Generar WEBHOOK_SECRET:
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Pegar en .env -> WEBHOOK_SECRET=...

# 4) Verificar el entorno antes de levantar nada
python scripts/doctor.py

# 5) Levantar LocalStack y esperar el healthcheck
docker compose up -d

# 6) Smoke real con Boto3 (crea y limpia recursos efímeros)
python scripts/check_localstack.py
```

- `scripts/doctor.py` comprueba Python, `.env`, variables obligatorias, destino loopback, imagen, Docker/Compose y salud del emulador. **No imprime secretos.**
- `scripts/check_localstack.py` valida SQS + DLQ, S3 con tags y EC2 mock (`stop`/`start`) contra LocalStack real.
- Las versiones efectivas están fijadas en `requirements-lock.txt` (generado con `pip freeze --exclude-editable`). No editarlo a mano.
- Para reinstalar exactamente lo probado: `python -m pip install -r requirements-lock.txt`.

## 5. Variables de entorno (sin valores privados)

Ver `.env.example` (plantilla canónica). Completar en `.env` local (nunca commitear):

| Variable | Obligatoria | Valor / nota |
|---|---:|---|
| `AWS_ENDPOINT_URL` | sí | `http://localhost:4566` (solo loopback, sin credenciales en la URL) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | sí | `test` / `test` (credenciales ficticias del emulador) |
| `AWS_DEFAULT_REGION` | sí | `us-east-1` (no usar `AWS_REGION`) |
| `GROUP_ID` / `QUEUE_PREFIX` | sí | Patrón `[a-z0-9-]{3,32}` |
| `PROJECT` | no | `fenix` (etiqueta de recursos; documental) |
| `WEBHOOK_SECRET` | sí | Generado con `secrets.token_urlsafe(32)`; mínimo 16 caracteres |
| `NOTIFY_PROVIDER` | sí | `console` (por defecto) · `telegram` · `slack` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | si `telegram` | Credenciales del bot |
| `SLACK_WEBHOOK_URL` | si `slack` | Incoming Webhook |
| `LOCALSTACK_IMAGE` | sí | `localstack/localstack:3.8.0` (sin token) |
| `LOCALSTACK_AUTH_TOKEN` | no | Solo si se adopta una imagen 2026+ |

> **Canal elegido: Telegram** (crear bot con @BotFather, obtener `chat_id`, llamar `sendMessage`). Slack queda como alternativa descartada; la decisión está en [`docs/DECISIONES.md`](docs/DECISIONES.md). El default local sigue siendo `console` para no exigir credenciales.
>
> **Trampa frecuente:** `python-dotenv` **no sobrescribe** variables ya exportadas en la terminal. Si un cambio en `.env` “no toma”, revisar `env | grep AWS_` o abrir una terminal nueva.

## 6. Arquitectura (Mermaid)

```mermaid
flowchart LR
  A[Monitor simulado / Cliente] -->|POST /webhook + HMAC raw bytes| B[Receiver FastAPI]
  B -->|valida contrato + inventario| C{¿OK?}
  C -- 401/400/413/422 --> D[Rechazo HTTP - no publica]
  C -- 202 + event_id/message_id --> E[(SQS eventos)]
  E --> F[Worker]
  F -->|consulta estado real| G[EC2 mock / S3 via Boto3+LocalStack]
  F -->|repara y verifica| G
  F -->|avisa resultado| H[Telegram o Slack]
  F -->|ledger durable data/events.json| I[(Estado local)]
  F -->|ACK delete_message tras éxito| E
  E -. fallos persistentes / RedrivePolicy .-> J[(DLQ)]
  K[QueueHandler/Listener -> JSON logs] -.-> L["logs/*.log(.gz)"]
```

> **Hito 4 (flujo completo):** el diagrama describe el sistema terminado. En la base actual, los nodos de validación (I1), publicación (I2), receptor/reparación (I3), aviso (I4) y worker (I5) todavía lanzan `NotImplementedError`; el receptor y el worker ya están cableados. La lista de funciones pendientes está en [`docs/ROLES.md`](docs/ROLES.md).

## 7. Contratos de entrada/salida

### Evento (JSON cerrado)
```json
{
  "schema_version": 1,
  "event_id": "evt-node-001",
  "event_type": "instance.stopped",
  "resource_id": "node-01",
  "occurred_at": "2026-10-22T18:00:00Z",
  "simulate_failures": 0
}
```
- `event_id` / `resource_id`: `[a-z0-9-]{3,32}`.
- `event_type`: `instance.stopped` | `bucket.tags_missing` (compatible con inventario).
- `simulate_failures`: entero 0-5 (nunca `bool`). Cuenta persistida en disco.
- Webhook acepta **aliases** conocidos (`node-01`, `bucket-01`), no IDs arbitrarios.

### Firma HMAC
`HMAC-SHA256(secret, bytes(t) + b"." + raw_body)`  
Cabecera: `X-Webhook-Signature: t=<epoch>,v1=<64 hex>` (ventana 300s).

### Orden del receptor y correlación

1. Rechaza el cuerpo que excede 16 KiB con **413**; aplica el conteo también a
   transferencias sin `Content-Length` confiable.
2. Exige una sola cabecera `X-Webhook-Signature`, verifica `t`/`v1` estrictos y
   el HMAC sobre los bytes originales. Cualquier fallo de autenticación es
   **401**, sin exponer si falló formato, tiempo o digest.
3. Solo con firma válida decodifica UTF-8 y JSON estricto (**400**) y después
   valida el contrato cerrado y el alias del inventario (**422**).
4. Resuelve la cola y ejecuta el `send_message` síncrono de Boto3 mediante un
   hilo de trabajo, esperando su `MessageId`. Un error de SQS/configuración es
   **503**: nunca se responde aceptación sin persistencia confirmada.
5. Recién entonces devuelve **202** con `event_id` y `message_id`. El primero
   también viaja como atributo SQS `EventId` y es la correlación con worker,
   ledger y logs. El receptor no repara ni notifica.

El límite tiene precedencia sobre la firma para limitar consumo de recursos;
para los cuerpos dentro del límite la autenticación precede todo parseo JSON.

### Respuestas HTTP del receptor
| Situación | HTTP | Efecto |
|---|---:|---|
| Firma ausente/malformada/incorrecta/fuera de ventana | 401 | No publicar |
| Cuerpo > 16 KiB | 413 | No publicar |
| JSON roto o UTF-8 inválido (firma válida) | 400 | No publicar |
| JSON válido pero contrato incorrecto | 422 | No publicar |
| SQS no disponible tras validar | 503 | No prometer aceptación |
| `send_message` confirmado por SQS | 202 | Devuelve `event_id`/`message_id`; worker procesa después |

## 8. Ejecución por terminal

```bash
# Preparar colas e inventario (idempotente)
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli fault node-01

# Terminal 1: receptor (1 worker)
python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env

# Terminal 2: worker
python -m fenix.cli worker

# Terminal 3: enviar alerta firmada
python -m fenix.cli send examples/node-event.json
```

> Actualizar `occurred_at` en ejemplos para evidencias claras; la CLI genera timestamp HMAC nuevo al enviar.

## 9. Reglas de reintento y DLQ

- Cola estándar SQS + **DLQ** con `RedrivePolicy` (`maxReceiveCount=3`).
- `VisibilityTimeout=45`, long polling 10s.
- Backoff por recepción: `min(30, 2 ** numero_de_recepcion)` (2, 4, 8...).
- **No** reenviar con `send_message` nuevo al reintentar; **no** borrar mensajes venenosos para ocultarlos.
- ACK (`delete_message` con `ReceiptHandle` actual) **solo después** de reparar y notificar con éxito durable.

## 10. Decisiones de idempotencia

- `event_id` identifica la operación de negocio. Ledger en `data/events.json` registra `attempts`, `repair_done`, `repair_result`, `notified`, `status`.
- Repetir el mismo evento (o reiniciar worker) no repite acciones ya verificadas: se consultan estados reales y se retoman pasos pendientes (ej. reenviar aviso sin re-reparar).
- Mismo `event_id` con contenido distinto → conflicto registrado; conservar para DLQ; no alterar primer registro.

## 11. Matriz de pruebas (F01–F16) — completar

| ID | Caso | Preparación | Resultado esperado | Resultado obtenido | Evidencia | Responsable | Fecha |
|---|---|---|---|---|---|---|---|
| F01 | init-queues/setup-demo x2 | `init-queues` x2 + `setup-demo` x2 | Mismas colas/recursos; sin duplicados | Mismas URLs de cola; mismo `InstanceId`, SG y bucket; 0 duplicados | [`evidence/F01-init-queues-idempotente.md`](evidence/F01-init-queues-idempotente.md) | I2 | 2026-11-12 |
| F02 | Nodo detenido → alerta válida | _Completar_ | Running verificado, ledger completo, aviso y ACK | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F03 | Bucket sin tag Owner | _Completar_ | Tags restauradas; ajenas preservadas | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F04 | Firma ausente/alterada/timestamp viejo | _Completar_ | 401; ningún mensaje nuevo | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F05 | Mismos datos, bytes distintos tras firmar | _Completar_ | 401 por HMAC inválida | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F06 | JSON roto firmado; lista JSON firmada | _Completar_ | 400 y 422; sin publicación | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F07 | Alias ajeno y claves extra | _Completar_ | Rechazo; ningún cambio cloud | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F08 | JSON corrupto inyectado directo a SQS | _Completar_ | Worker sigue; mensaje termina en DLQ | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F09 | `simulate_failures=2` (ID nuevo) | _Completar_ | Backoff; luego reparación y ACK | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F10 | Falla persistente (ID nuevo) | _Completar_ | Sin ACK; derivación a DLQ | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F11 | Repetir evento completo; reiniciar worker | _Completar_ | Sin nueva reparación ni aviso confirmado | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F12 | Cortar tras `repair_done` antes de `notify` | _Completar_ | Reinicio recupera solo aviso pendiente | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F13 | SQS detenido al recibir webhook | _Completar_ | 503; no aceptación falsa | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F14 | Mock aviso 429/timeout luego éxito | _Completar_ | No repite reparación; reintenta aviso | _Completar_ | _Completar_ | _Completar_ | _Completar_ |
| F15 | Cambiar payload conservando `event_id` | `handle` dos veces con distinto contenido | Conflicto; no altera ledger/recursos originales | Conflicto en `_conflicts`; registro original y recursos intactos; sin ACK | `tests/test_i5_worker.py::test_handle_registra_conflicto_sin_cambiar_el_original` | I5 | 2026-11-13 |
| F16 | Forzar rotación, leer `.gz`, parsear líneas | _Completar_ | JSON válido, UTC, contexto; sin secretos | _Completar_ | _Completar_ | _Completar_ | _Completar_ |

> Automáticas sugeridas: F04,F05,F06,F07,F09,F11/F12,F16. Integración LocalStack: F01,F02,F03,F08,F10,F13.
>
> **Cómo completar la matriz:** cada fila se cierra con un archivo en [`evidence/`](evidence/README.md) (fecha, comando, salida real sin secretos) y, si corresponde, una captura en `docs/images/`. **I6** custodia la matriz completa y valida la asignación de casos F; cada rol aporta la evidencia de sus funciones. No se completa con “funcionó”: hace falta comando + resultado.

## 12. Limitaciones

1. **EC2 mock no es una VM real:** `EC2_VM_MANAGER=mock` no reproduce latencias ni fallos de hardware. Los reintentos y el backoff se demuestran con `simulate_failures` y la DLQ.
2. **VPC default:** se usa la VPC predeterminada del emulador por simplicidad de laboratorio; en producción se usaría una VPC propia con subredes y SG acotados.
3. **Un solo writer sobre `data/`:** `data/events.json` no tiene bloqueo entre procesos. No correr dos workers sobre el mismo proyecto.
4. **Estado efímero:** LocalStack no usa volumen persistente; `docker compose down` borra colas, buckets e instancias. Hay que repetir `init-queues` y `setup-demo`.
5. **Aviso potencialmente duplicado:** si el worker muere después de enviar la notificación y antes de persistir `notified`, el reinicio puede reenviarla. No se promete *exactly-once*.
6. **Ventana HMAC:** los 300 s rechazan entregas viejas, pero **no** impiden repetir un evento válido dentro de la ventana; para eso está `event_id` + ledger.
7. **`python-dotenv` no sobrescribe** variables ya exportadas en la terminal.
8. **Notificación sujeta a terceros:** la disponibilidad de Telegram/Slack no depende del equipo; 429 y 5xx se reintentan con tope de `Retry-After` de 30 s.
9. **Logs sin `exc_info`:** `JSONFormatter` de apoyo no serializa trazas; si se necesitan, I4 debe acordar el cambio (ver [`docs/DECISIONES.md`](docs/DECISIONES.md)).

## 13. Evidencia del canal elegido (Telegram)

**Canal elegido: Telegram** (`NOTIFY_PROVIDER=telegram`). El default local sigue siendo `console` para trabajar sin credenciales.

_Evidencia a cargo de I4: captura anonimizada del mensaje recibido (ocultar token y `chat_id`), fecha/hora y comando usado._

## 14. Limpieza del laboratorio

```text
# Completar con comandos/pasos usados:
# - Terminar instancia inventariada
# - Vaciar y borrar bucket inventariado
# - Eliminar security group cuando no esté en uso
# - Destruir colas solo después de documentar la DLQ
# - docker compose down (si aplica)
```

## 15. Video y marcas de tiempo

| Integrante | Marca de tiempo | Contenido |
|---|---|---|
| Herrera Nancy Mariel (I1) | 00:00 | _Completar_ |
| Maldonado, Fernando Manuel (I2) | 00:00 | _Completar_ |
| Mamani, Hector Mauricio (I3) | 00:00 | _Completar_ |
| Alegre, Facundo Sebastián (I4) | 00:00 | _Completar_ |
| Rodríguez, Hector Fernando (I5) | 00:00 | _Completar_ |
| Gaspar Lautaro Miguel Angel (I6) | 00:00 | _Completar_ |

Link al video: _Completar_

## 16. Declaración de ayuda externa e IA

_Completar: herramientas/IA utilizadas, qué se generó o modificó, cómo se verificó, y confirmar que cada integrante puede explicar y modificar su código._

## 17. Estructura del repositorio

```text
fenix/
├── compose.yaml                  # LocalStack 3.8.0 + healthcheck + EC2 mock
├── pyproject.toml                # Paquete, dependencias y marcadores de pytest
├── requirements.txt              # Dependencias declaradas
├── requirements-lock.txt         # Versiones efectivas (pip freeze)
├── .env.example                  # Plantilla de variables (sin secretos)
├── .python-version               # 3.14
├── README.md                     # Entrega formal
├── CONTRIBUTING.md               # Ramas, commits, PR y reglas de código
├── architecture.png              # Diagrama de arquitectura
├── docs/
│   ├── ROLES.md                  # Qué hace cada rol, archivos, pruebas y DoD
│   ├── ENTORNO.md                # Instalación, LocalStack y problemas frecuentes
│   ├── DECISIONES.md             # Decisiones de diseño y limitaciones
│   └── GUIA_DEFENSA.md           # Guion del video y modificaciones en vivo
├── evidence/                     # Evidencia reproducible F01–F16
├── examples/                     # Eventos de ejemplo firmables
├── scripts/
│   ├── doctor.py                 # Diagnóstico del entorno (sin secretos)
│   └── check_localstack.py       # Smoke real SQS/S3/EC2 con limpieza
├── src/fenix/
│   ├── cli.py                    # init-queues, setup-demo, fault, worker, send
│   ├── config/settings.py        # Guardián loopback + timeouts (congelado)
│   ├── services/
│   │   ├── events.py             # I1: contrato del evento
│   │   ├── sqs.py                # I2: colas, publish, receive, ACK, backoff
│   │   ├── demo.py               # I2: setup_demo · I6: inject_fault
│   │   ├── receiver.py           # I3: POST /webhook
│   │   ├── remediation.py        # I3: repair · I5: handle
│   │   ├── notifications.py      # I4: notify
│   │   ├── worker.py             # I5: run
│   │   └── cloud_support.py      # Recetas Boto3 (apoyo)
│   └── utils/
│       ├── validation.py         # I1: identifier, ttl_seconds, utc_text
│       ├── crypto.py             # I3: verify HMAC
│       ├── state.py              # Ledger atómico (apoyo)
│       ├── errors.py             # Jerarquía de errores (apoyo)
│       └── logging_json.py       # Logs JSON con rotación (apoyo)
├── tests/
│   ├── test_base.py              # Apoyo del template (marca base)
│   ├── test_contracts.py         # Contratos I1 (marca pendiente)
│   ├── test_fenix.py             # HMAC sobre bytes crudos
│   └── test_scenarios.py         # Escenarios e integración
└── .github/
    ├── workflows/ci.yml          # Tests base + compose config + doctor
    └── pull_request_template.md  # Checklist de PR
```

## 18. Estado por rol

La base está **endurecida y verificada localmente**, pero la lógica de negocio sigue pendiente: hay **14 funciones con `NotImplementedError`**, repartidas así:

| Rol | Integrante | Funciones pendientes | Archivos |
|---|---|---|---|
| I1 | Herrera, Nancy Mariel | `identifier`, `ttl_seconds`, `utc_text`, `validate` | `utils/validation.py`, `services/events.py` |
| I2 | Maldonado, Fernando Manuel | `ensure_queues`, `retry_later`, `setup_demo` | `services/sqs.py`, `services/demo.py` |
| I3 | Mamani, Hector Mauricio | `verify`, endpoint `/webhook`, `repair` | `utils/crypto.py`, `services/receiver.py`, `services/remediation.py` |
| I4 | Alegre, Facundo Sebastián | `notify` | `services/notifications.py` |
| I5 | Rodríguez, Hector Fernando | `run`, `handle` | `services/worker.py`, `services/remediation.py`, `cli.py` |
| I6 | Gaspar, Lautaro Miguel Angel | `inject_fault` + suite F01–F16 | `services/demo.py`, `tests/` |

**Estado de la suite hoy:**

| Comando | Resultado |
|---|---|
| `pytest -m base -q` | **4 passed** (apoyo del template) |
| `pytest -m pendiente -q` | 6 failed (esperado hasta completar roles) |
| `pytest -m integracion -q` | 1 failed (requiere LocalStack y rol 5/6) |

> El orden de trabajo recomendado es I1 → I2 → I3 → I5 → I4 → I6. I4 puede arrancar en paralelo porque solo depende de su propio módulo. Detalle y definición de terminado en [`docs/ROLES.md`](docs/ROLES.md).

## 19. Documentación del equipo

| Documento | Para qué sirve |
|---|---|
| [`docs/ROLES.md`](docs/ROLES.md) | Asignación, contratos, pruebas y definición de terminado por rol |
| [`docs/ENTORNO.md`](docs/ENTORNO.md) | Instalación desde cero, LocalStack/token y problemas frecuentes |
| [`docs/DECISIONES.md`](docs/DECISIONES.md) | Decisiones de diseño, alternativas descartadas y limitaciones |
| [`docs/GUIA_DEFENSA.md`](docs/GUIA_DEFENSA.md) | Guion del video (30–40 min) y modificaciones en vivo |
| [`tests/README.md`](tests/README.md) | Estado de la suite, comandos y cobertura esperada |
| [`evidence/README.md`](evidence/README.md) | Convención y plantilla de evidencia F01–F16 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Ramas, commits, PR, reglas de código y revisión cruzada |

> **Revisión cruzada obligatoria:** I1↔I6, I2↔I5, I3↔I4. Cada PR necesita al menos una aprobación registrada en GitHub antes del merge.
>
> **Repositorio:** `fenix-autorepair`. La publicación en GitHub se hace recién cuando la base local esté aprobada por el grupo.
