# Trabajo por rol — Proyecto Fénix

Documento operativo del equipo. El `README.md` es la entrega formal; este archivo
explica **qué hace cada integrante, con qué archivos, qué pruebas defiende y
cuándo su trabajo está terminado**.

> Regla de oro: **un rol = una rama = un pull request**. Nadie implementa el
> módulo de otro. Las revisiones cruzadas son obligatorias (ver el final).

## 1. Reglas comunes

- Solo se modifican los archivos asignados al rol. Los archivos de apoyo están
  congelados (ver sección 2).
- Prohibido `except: pass`, capturar `BaseException` y usar `return`, `break` o
  `continue` dentro de `finally`.
- Toda llamada de red lleva timeout acotado (conexión y lectura).
- No se commitean `.env`, `.venv/`, `data/`, `logs/`, tokens ni capturas con
  secretos.
- Cada PR debe dejar `pytest -m base -q` en verde y sumar las pruebas del rol.
- Commits identificables: `rol N: ...`, `test: ...`, `docs: ...`, `fix: ...`,
  `chore: ...`.
- Si un cambio afecta a otro rol, se acuerda en el PR; no se mergea por sorpresa.

## 2. Archivos congelados (no tocar sin acuerdo)

| Archivo | Motivo |
|---|---|
| `src/fenix/config/settings.py` | Guardián loopback y timeouts comunes |
| `src/fenix/utils/state.py` | Escritura atómica del ledger |
| `src/fenix/utils/errors.py` | Jerarquía de errores del dominio |
| `src/fenix/utils/logging_json.py` | Pipeline de logs; lo verifica I4 |
| `src/fenix/services/cloud_support.py` | Recetas Boto3 entregadas |
| `compose.yaml`, `pyproject.toml`, `.env.example` | Infraestructura compartida |

## 3. Orden de dependencias

```
I1 ──> I2 ──> I3 ──> I5 ──> I6
                 └──> I4 ──┘
```

- **I1** no depende de nadie: puede arrancar ya.
- **I2** necesita `identifier()` de I1 para `setup_demo`.
- **I3** necesita `validate()` de I1 y `queue_url`/`publish` de I2 (ya implementados).
- **I4** es independiente: puede arrancar en paralelo.
- **I5** necesita I1, I2, I3 e I4.
- **I6** puede escribir pruebas con fakes desde el inicio, pero la matriz completa
  se cierra al final.

## 4. Resumen

| Rol | Integrante | Rama | Archivos propios | Funciones | Casos F (propuesta) |
|---|---|---|---|---|---|
| I1 | Herrera, Nancy Mariel | `rol1-entradas` | `utils/validation.py`, `services/events.py` | `identifier`, `ttl_seconds`, `utc_text`, `validate` | F06, F07, F15 |
| I2 | Maldonado, Fernando Manuel | `rol2-mensajeria` | `services/sqs.py`, `services/demo.py` (`setup_demo`) | `ensure_queues`, `retry_later`, `setup_demo` | F01, F09, F10 |
| I3 | Mamani, Hector Mauricio | `rol3-webhooks` | `utils/crypto.py`, `services/receiver.py`, `remediation.repair` | `verify`, endpoint `/webhook`, `repair` | F02, F03, F04, F05, F06, F13 |
| I4 | Alegre, Facundo Sebastián | `rol4-observabilidad` | `services/notifications.py` | `notify` | F14, F16 |
| I5 | Rodríguez, Hector Fernando | `rol5-worker` | `services/worker.py`, `remediation.handle`, `cli.py` | `run`, `handle` | F02, F03, F08, F09, F11, F12, F15 |
| I6 | Gaspar, Lautaro Miguel Angel | `rol6-tests` | `tests/`, `services/demo.py` (`inject_fault`) | `inject_fault` + suite F01–F16 | F01–F16 |

> La asignación de casos F es una **propuesta**; I6 la valida y completa la
> columna "Resultado obtenido" de la matriz del README.

---

## I1 — Entradas y excepciones

**Objetivo:** que ningún dato inválido entre al sistema y que los errores sean
visibles, tipados y sin filtrar secretos.

**Archivos:** `src/fenix/utils/validation.py`, `src/fenix/services/events.py`.

**Funciones:**

| Función | Contrato |
|---|---|
| `identifier(value)` | `str`, patrón `[a-z0-9-]{3,32}`, sin normalizar mayúsculas |
| `ttl_seconds(value)` | entero entre 60 y 600 inclusive; rechaza decimales y texto |
| `utc_text(value)` | ISO 8601 con `Z` o `+00:00`; rechaza fechas ingenuas y offsets no nulos |
| `validate(event, inventory)` | esquema cerrado, `schema_version == 1` (int, no bool), `event_type` permitido, `resource_id` solo alias del inventario y tipo coherente, `simulate_failures` int 0–5 (no bool) |

**Pruebas que defiende:** `tests/test_contracts.py` (3 casos) + las que agregue
en `tests/test_i1_entradas.py`.

**Dependencias:** ninguna. **Habilita a:** I2, I3, I5.

**Definición de terminado:**
- Las 4 funciones implementadas y con docstring actualizado.
- `pytest -m base` sigue verde y los contratos de I1 pasan.
- Los rechazos usan `ValidationError` con mensaje genérico (sin eco del valor).
- Sin `except: pass` ni capturas amplias.

**Modificación en vivo (defensa):**
- Cambiar el regex para aceptar mayúsculas y mostrar que el contrato falla.
- Agregar una clave extra al evento y mostrar el rechazo por esquema cerrado.
- Enviar `simulate_failures: true` y mostrar que no se acepta como entero.

---

## I2 — Mensajería e inventario cloud

**Objetivo:** dejar el broker listo (cola + DLQ) y un laboratorio reproducible
(instancia EC2 mock + bucket S3) con inventario durable.

**Archivos:** `src/fenix/services/sqs.py`, `src/fenix/services/demo.py`
(únicamente `setup_demo`; `inject_fault` es de I6).

**Funciones:**

| Función | Contrato |
|---|---|
| `ensure_queues(prefix)` | crear primero la DLQ y después `{prefix}-events`; `VisibilityTimeout=45`, retención 345600, DLQ 1209600, `RedrivePolicy` con `maxReceiveCount=3`; forzar la política con `set_queue_attributes`; devolver URLs del SDK |
| `retry_later(url, message)` | leer `ApproximateReceiveCount`, calcular `min(30, 2 ** count)`, llamar `change_message_visibility` con el `ReceiptHandle` actual y devolver los segundos; **nunca** `send_message` |
| `setup_demo(group)` | validar `group`, VPC default, AMI mock, SG con tags, instancia con `ClientToken` estable, bucket con tags y `data/inventory.json`; `node-01` guarda `security_group_id` y `expected_tags`; `bucket-01` guarda `expected_tags`; reutilizar por tags antes de crear |

**Pruebas que defiende:** `tests/test_i2_mensajeria.py` + el escenario de redrive
real (`tests/test_scenarios.py::test_redrive_with_localstack`, custodiado por I6).

**Dependencias:** `identifier()` de I1. **Habilita a:** I3 (receptor) e I5 (worker).

**Definición de terminado:**
- `init-queues` y `setup-demo` son idempotentes: correrlos dos veces no duplica.
- La DLQ recibe el mensaje tras 3 recepciones fallidas.
- El inventario guarda IDs reales del emulador, no IDs inventados.
- Los tags obligatorios están presentes: `ManagedBy=ppa2`, `Project=fenix`,
  `GroupId=<grupo>`, `Owner=<grupo>`.

**Modificación en vivo (defensa):**
- Bajar `maxReceiveCount` a 1 y mostrar que el mensaje cae en la DLQ.
- Cambiar la base del backoff y mostrar `1, 2, 4`.
- Ejecutar `setup-demo` dos veces y comparar los IDs del inventario.

---

## I3 — Webhooks y reparación

**Objetivo:** autenticar el webhook sobre los bytes originales, aceptar solo
eventos válidos y converger el recurso al estado deseado verificando por API.

**Archivos:** `src/fenix/utils/crypto.py`, `src/fenix/services/receiver.py`,
`src/fenix/services/remediation.py` (solo `repair`).

**Funciones:**

| Función | Contrato |
|---|---|
| `verify(secret, header, body, now=None)` | parsear `t=<epoch>,v1=<hex>` exigiendo cada clave una sola vez; `t` entero; `v1` 64 hex; ventana `abs(now - t) <= 300`; `hmac.compare_digest`; `ValidationError` genérico |
| `POST /webhook` | leer bytes crudos; 413 si > 16 KiB; 401 firma; 400 JSON/UTF-8; 422 contrato; 503 si SQS falla; 202 con `event_id` y `message_id` solo tras `send_message` |
| `repair(resource, event_type)` | EC2: `running -> already_ok`, `stopped -> start`, `pending -> RetryableError`, `stopping/terminated -> error`; S3: combinar tags, preservar ajenas, `NoSuchTagSet` = vacío, releer y verificar; clasificar `ClientError` |

**Pruebas que defiende:** `tests/test_fenix.py` (HMAC sobre bytes crudos) +
`tests/test_i3_webhooks.py` (TestClient de FastAPI).

**Dependencias:** I1 (`validate`) e I2 (`queue_url`, `publish`).

**Definición de terminado:**
- El receptor no re-serializa el JSON antes de verificar.
- Los seis códigos HTTP (401/413/400/422/503/202) están cubiertos.
- `repair` verifica el estado final por API; no devuelve éxito sin comprobarlo.
- Ningún mensaje de error incluye el secreto ni la cabecera completa.

**Modificación en vivo (defensa):**
- Bajar la ventana a 10 s y mostrar 401 con un timestamp viejo.
- Firmar un JSON con otros espacios y mostrar 401.
- Quitar la relectura de tags y mostrar que la verificación falla.

---

## I4 — Observabilidad y comunicación

**Objetivo:** que el aviso salga solo cuando el proveedor lo confirme y que los
logs sean JSON correlacionados, con rotación y sin secretos.

**Archivos:** `src/fenix/services/notifications.py`. Verificación de
`src/fenix/utils/logging_json.py` (archivo de apoyo; si hay un bug, se acuerda el
fix en el PR).

**Funciones:**

| Función | Contrato |
|---|---|
| `notify(text)` | `console` imprime; Telegram `sendMessage` exige HTTP 200 y `ok is True`; Slack exige HTTP 200 y body textual `ok`; `timeout=(2, 5)`; 429/5xx `RetryableError`; `Retry-After` con tope 30 s; otros 4xx `PermanentError`; no registrar la excepción original |

**Pruebas que defiende:** `tests/test_i4_observabilidad.py` con `requests.post`
monkeypatcheado.

**Dependencias:** ninguna. **Habilita a:** I5.

**Riesgo conocido:** `JSONFormatter` no serializa `exc_info`. Si el equipo
necesita trazas en el log, I4 debe proponer el cambio y acordarlo (no es un
cambio unilateral).

**Definición de terminado:**
- El modo `console` sigue funcionando sin credenciales.
- 429, timeout y 5xx se reintentan; 400/401/403 no.
- El texto se recorta a 1000 caracteres y nunca incluye tokens.
- La evidencia del canal real queda en `docs/images/` y en el README.

**Modificación en vivo (defensa):**
- Simular 429 con `Retry-After: 99` y mostrar el tope de 30 s.
- Simular 200 con `ok=false` y mostrar `PermanentError`.
- Quitar el token y mostrar que no se reintenta infinitamente.

---

## I5 — Integración y worker

**Objetivo:** consumir SQS, ejecutar el caso de negocio y confirmar (ACK) solo
después de que reparación y aviso quedaron durables.

**Archivos:** `src/fenix/services/worker.py`,
`src/fenix/services/remediation.py` (`handle`), `src/fenix/cli.py`.

**Funciones:**

| Función | Contrato |
|---|---|
| run(url, handler, logger, once=False) | bucle; receive en try; por mensaje, contexto con message_id y attempt (ApproximateReceiveCount) antes de json.loads; exigir dict; agregar event_id, resource_id y action al contexto de cada log; ACK solo tras éxito; JSON/validación/negocio/red -> retry_later; fallo de ACK deja el mensaje disponible; nunca ACK en finally; once hace una consulta; NotImplementedError se propaga |
| handle(event) | cargar inventario y validar; ledger por event_id; vincular ID y contenido; incrementar attempts antes de simular fallas; si attempts <= simulate_failures -> RetryableError sin tocar recursos; reparar si falta; notificar si falta; no repetir etapas completas; cada save preserva el resto del ledger; si el event_id reaparece con otro contenido, registrar el conflicto en _conflicts y conservarlo para la DLQ sin modificar el primer registro ni los recursos |

**Pruebas que defiende:** `tests/test_i5_worker.py` (fakes de SQS) +
`test_scenarios.py::test_duplicate_is_idempotent` y `test_ack_is_after_success`
(custodiados por I6).

**Dependencias:** I1, I2, I3 e I4.

**Definición de terminado:**
- Un handler fallido no genera ACK.
- Un JSON corrupto no mata el worker y termina en la DLQ.
- Reiniciar el worker retoma el paso pendiente sin repetir la reparación.
- `attempts` sobrevive al reinicio porque está en `data/events.json`.

**Modificación en vivo (defensa):**
- Hacer que el handler lance y mostrar cero ACK.
- Inyectar `simulate_failures=2` y mostrar los intentos persistidos.
- Cortar el proceso después de `repair_done` y mostrar que al reiniciar solo
  notifica.

---

## I6 — Pruebas y diagnóstico

**Objetivo:** demostrar con evidencia que el sistema cumple la matriz F01–F16 y
fabricar los fallos de laboratorio sin aceptar IDs arbitrarios.

**Archivos:** `tests/` (incluye `conftest.py` y `tests/README.md`) y
`src/fenix/services/demo.py` (`inject_fault`).

**Funciones:**

| Función | Contrato |
|---|---|
| `inject_fault(alias)` | resolver el alias en `data/inventory.json`; `node-01`: `stop_instances` y verificar `stopped`; `bucket-01`: quitar `Owner` conservando el resto; nunca aceptar un `InstanceId` libre; no enviar el evento automáticamente |

**Pruebas que defiende:** toda la suite + la matriz F01–F16 con fecha, comando,
resultado esperado, resultado obtenido y evidencia.

**Dependencias:** todos los roles. Puede empezar con fakes y `botocore.stub.Stubber`.

**Definición de terminado:**
- `pytest -m base` verde y la suite de escenarios ejecutable.
- La matriz del README está completa, con evidencia en `evidence/`.
- El redrive se demuestra contra LocalStack, no con una lista en memoria.
- Los logs rotados se leen y parsean como JSON.

**Modificación en vivo (defensa):**
- Cambiar una expectativa de un test y mostrar que falla.
- Forzar `maxReceiveCount=1` y mostrar el mensaje en la DLQ.
- Corromper un JSON inyectado directo a SQS y mostrar que el worker sigue vivo.

---

## 5. Revisión cruzada (obligatoria)

| Rol | Revisa a |
|---|---|
| I1 | I6 |
| I2 | I5 |
| I3 | I4 |
| I4 | I3 |
| I5 | I2 |
| I6 | I1 |

Cada PR debe tener al menos **una aprobación** del compañero asignado antes del
merge. La revisión se registra en GitHub; no alcanza con un comentario oral.

## 6. Definición de terminado global

Un rol está terminado cuando:

1. Sus funciones ya no lanzan `NotImplementedError`.
2. Sus pruebas pasan y `pytest -m base` sigue verde.
3. El PR tiene revisión cruzada aprobada.
4. No hay secretos, rutas absolutas ni `except: pass`.
5. La documentación de su sección y la evidencia F correspondiente están
   actualizadas.
6. El integrante puede explicar y **modificar en vivo** su módulo.
