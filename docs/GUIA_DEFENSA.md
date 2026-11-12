# Guía de defensa — Proyecto Fénix

## 1. Formato

- Video grupal de **30 a 40 minutos**.
- **5 a 7 minutos por integrante**, en el orden de dependencias:
  I1 → I2 → I3 → I5 → I4 → I6.
- Cada bloque debe mostrar: contexto, módulo, demo en vivo, **modificación en
  vivo** y pruebas que defiende.

## 2. Rúbrica

**Grupal (100 puntos):** flujo 25 · mensajería 20 · validación 15 ·
observabilidad 15 · documentación 10 · pruebas 15.

**Individual:** módulo 40 · ejecución 30 · **modificación en vivo 20** ·
comunicación 10.

La modificación en vivo es el 20%: no alcanza con explicar; hay que cambiar algo
y demostrar el efecto.

## 3. Guion por rol

### I1 — Entradas y excepciones (5–7 min)

- **Contexto:** ninguna entrada inválida debe llegar a SQS.
- **Mostrar:** `identifier`, `ttl_seconds`, `utc_text`, `validate`.
- **Demo:** `pytest -m pendiente -q` antes/después; enviar un evento con alias
  ajeno y mostrar 422.
- **Modificación en vivo:** cambiar el regex para aceptar mayúsculas y mostrar
  que el contrato falla; agregar una clave extra y mostrar el rechazo.
- **Cierre:** los rechazos son `ValidationError` genéricos, sin eco de datos.

### I2 — Mensajería e inventario cloud (5–7 min)

- **Contexto:** broker con DLQ y laboratorio reproducible.
- **Mostrar:** `init-queues`, `setup-demo`, `retry_later`, tags.
- **Demo:** `python -m fenix.cli init-queues` dos veces; `setup-demo` dos veces y
  comparar IDs; `describe` de la cola con `RedrivePolicy`.
- **Modificación en vivo:** bajar `maxReceiveCount` a 1 y mostrar la DLQ;
  cambiar la base del backoff y mostrar `1, 2, 4`.
- **Cierre:** nunca se reenvía con `send_message` al reintentar.

### I3 — Webhooks y reparación (5–7 min)

- **Contexto:** autenticación sobre bytes crudos y convergencia verificada.
- **Mostrar:** `verify`, `/webhook`, `repair`.
- **Demo:** firmar un evento, enviarlo con `cli send`, mostrar 202 y el mensaje
  en SQS; enviar firma alterada y mostrar 401.
- **Modificación en vivo:** bajar la ventana a 10 s y mostrar 401 con timestamp
  viejo; firmar un JSON con otros espacios y mostrar 401.
- **Cierre:** `repair` relee el estado; no devuelve éxito sin verificar.

### I4 — Observabilidad y comunicación (5–7 min)

- **Contexto:** el aviso sale solo si el proveedor lo confirma; logs JSON.
- **Mostrar:** `notify`, `JSONFormatter`, rotación `.gz`.
- **Demo:** `NOTIFY_PROVIDER=console` y luego Telegram/Slack real; mostrar el
  mensaje recibido y una línea JSON del log.
- **Modificación en vivo:** simular 429 con `Retry-After: 99` y mostrar el tope
  de 30 s; simular 200 con `ok=false` y mostrar `PermanentError`.
- **Cierre:** nunca se registra la excepción original (puede contener el token).

### I5 — Integración y worker (5–7 min)

- **Contexto:** ACK solo después de éxito durable.
- **Mostrar:** `run`, `handle`, ledger `data/events.json`.
- **Demo:** evento nominal completo; luego handler fallido y mostrar que el
  mensaje no se confirma.
- **Modificación en vivo:** inyectar `simulate_failures=2` y mostrar los intentos;
  cortar después de `repair_done` y mostrar que al reiniciar solo notifica.
- **Cierre:** no existe exactly-once; se documenta la ventana de resultado
  incierto.

### I6 — Pruebas y diagnóstico (5–7 min)

- **Contexto:** la matriz F01–F16 es la evidencia del sistema.
- **Mostrar:** `tests/`, `inject_fault`, `check_localstack.py`.
- **Demo:** correr la suite; mostrar un mensaje corrupto inyectado directo a SQS
  y cómo termina en la DLQ sin matar el worker.
- **Modificación en vivo:** cambiar una expectativa y mostrar el fallo; forzar
  `maxReceiveCount=1` y mostrar la DLQ.
- **Cierre:** el redrive se demuestra contra LocalStack, no con una lista en
  memoria.

## 4. Preguntas frecuentes

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué 3.8.0 y no la última? | Es la imagen del Lab-1; las 2026+ exigen token y el TP no lo requiere |
| ¿Por qué no FIFO? | El TP no exige orden estricto; la DLQ y la idempotencia cubren los fallos |
| ¿HMAC evita replay? | Solo rechaza entregas viejas; dentro de la ventana puede repetirse |
| ¿Cómo evitan duplicados? | `event_id` + ledger durable, no un `set` en memoria |
| ¿Qué pasa si el worker muere? | El mensaje vuelve a estar visible; el ledger retoma el paso pendiente |
| ¿Por qué no ACK al recibir? | Porque todavía no hay éxito durable; se perdería el evento |
| ¿Qué pasa si Telegram falla? | 429/5xx se reintentan; 4xx de configuración es permanente |
| ¿Por qué no re-serializan el JSON? | Otros bytes producen otra firma; se verifica sobre el cuerpo original |
| ¿Qué limitación asumen? | Mock, VPC default, un solo writer, estado efímero y posible aviso duplicado |

## 5. Checklist de evidencias

- [ ] `pytest -m base` verde.
- [ ] Suite del rol y casos F ejecutados con fecha y comando.
- [ ] Capturas en `docs/images/` sin tokens ni chat IDs.
- [ ] Mensaje real de Telegram/Slack (o justificación de `console`).
- [ ] Logs JSON y un archivo rotado `.gz` leído correctamente.
- [ ] Matriz F01–F16 del README completa.
- [ ] Video con marca de tiempo por integrante.
- [ ] Declaración de IA completa.
