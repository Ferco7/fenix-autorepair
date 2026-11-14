# Decisiones de diseño — Proyecto Fénix

Registro de las decisiones que el equipo defiende en la exposición. Cada una
incluye el porqué y la alternativa descartada.

## 1. LocalStack 3.8.0, sin token

**Decisión:** usar `localstack/localstack:3.8.0`, la imagen del Lab-1 de la
cátedra.

**Por qué:**
- La consigna dice *“Usar primero la instalación de LocalStack ya trabajada con
  la cátedra”* y *“Completar el token LocalStack solo si la imagen adoptada lo
  requiere”*. Es una condición, no un requisito.
- El mínimo obligatorio pide *“LocalStack en Docker, SQS estándar con DLQ, S3 y
  EC2 en modo mock”*. La 3.8.0 cubre los tres servicios, verificado con
  `scripts/check_localstack.py`.
- Las imágenes `2026.03+` exigen `LOCALSTACK_AUTH_TOKEN`; sin token el contenedor
  sale con código 55.

**Alternativa descartada:** `:latest` o `2026.10.0`. Introduce una dependencia
externa (token/plan) sin mejorar el alcance del TP.

**Si la cátedra lo pide:** se cambia `LOCALSTACK_IMAGE` y se completa el token en
`.env`. Cero cambios de código.

## 2. Alcance mínimo y EC2 mock

Se usa EC2 en modo mock (`EC2_VM_MANAGER=mock`). No hay VM real, ni credenciales
de AWS, ni red externa. El objetivo es demostrar convergencia por API, no
aprovisionar infraestructura real.

**Limitación:** el mock no reproduce latencias ni fallos de una VM real. Los
reintentos y el backoff se demuestran con `simulate_failures` y con la DLQ.

## 3. SQS estándar + DLQ

| Parámetro | Valor | Motivo |
|---|---|---|
| Tipo de cola | Estándar (no FIFO) | El TP no exige orden estricto |
| `VisibilityTimeout` | 45 s | Cubre reparación + notificación |
| Retención cola | 345600 s (4 días) | Ventana de trabajo del laboratorio |
| Retención DLQ | 1209600 s (14 días) | Conservar evidencia de fallos |
| `maxReceiveCount` | 3 | Deriva a DLQ tras 3 intentos |
| Long polling | 10 s | Evita polling intensivo |
| Backoff | `min(30, 2 ** recepcion)` | 2, 4, 8… con tope |

No se reenvía con `send_message` al reintentar: eso reiniciaría la cuenta de
recepciones y rompería la DLQ. Se usa `change_message_visibility` sobre el mismo
mensaje.

## 4. HMAC sobre bytes crudos

```
HMAC-SHA256(secret, str(t).encode() + b"." + raw_body)
Cabecera: X-Webhook-Signature: t=<epoch>,v1=<64 hex>
Ventana: |now - t| <= 300 s
```

- Se verifica **antes** de `json.loads` y sobre los bytes originales.
- No se re-serializa el JSON: un cambio de espacios produce otros bytes y otra
  firma.
- Se usa `hmac.compare_digest` para evitar cortocircuitos por contenido.
- La ventana mitiga replay viejo, pero **no** impide repetir un evento válido
  dentro de la ventana; para eso está `event_id` + ledger.

## 5. Idempotencia

- `event_id` identifica la operación de negocio.
- `data/events.json` guarda `attempts`, `repair_done`, `repair_result`,
  `notified` y `status` por evento.
- Repetir el mismo evento no repite reparación ni aviso ya confirmados.
- Mismo `event_id` con contenido distinto = conflicto; se conserva el primer
  registro y el mensaje se deriva a la DLQ.
- **No se promete exactly-once.** Un timeout al notificar puede duplicar el
  aviso: es la “ventana de resultado incierto” de la clase 5.

## 6. Códigos HTTP del receptor

| Situación | HTTP | Efecto |
|---|---:|---|
| Firma ausente, malformada, incorrecta o fuera de ventana | 401 | No publicar |
| Cuerpo > 16 KiB | 413 | No publicar |
| JSON roto o UTF-8 inválido (firma válida) | 400 | No publicar |
| JSON válido con contrato incorrecto | 422 | No publicar |
| SQS no disponible tras validar | 503 | No prometer aceptación |
| `send_message` confirmado | 202 | Devuelve `event_id` y `message_id` |

Primero se guarda durable en SQS; después se responde 2xx. Nunca al revés.
El cuerpo se limita antes de autenticar para contener consumo de memoria; dentro
del límite el orden es HMAC sobre bytes crudos → UTF-8/JSON → contrato e
inventario → SQS. La llamada Boto3 no es asíncrona: el handler la ejecuta en un
hilo de trabajo y espera el `MessageId` antes de devolver 202. `event_id` queda
en la respuesta y como atributo `EventId` de SQS para correlacionar receptor,
worker, ledger y logs sin registrar el cuerpo ni la firma.

## 7. Notificaciones

- Modo por defecto: `console` (desarrollo, sin credenciales).
- **Canal elegido por el grupo: Telegram.** `console` queda como default local para
  no exigir credenciales; la evidencia del mensaje real la aporta I4.
- Clasificación: timeout/conexión/429/5xx -> `RetryableError`; 400/401/403 ->
  `PermanentError`; `Retry-After` con tope de 30 s.
- El texto se recorta a 1000 caracteres y no incluye tokens ni el body crudo.
- Telegram exige HTTP 200 **y** `ok is True`; Slack exige HTTP 200 **y** body
  textual `ok`. Un 200 solo no alcanza.

## 8. Limitaciones asumidas

1. EC2 mock no es una VM real: no hay latencia ni fallos de hardware.
2. Se usa la VPC default del emulador; en producción se usaría una VPC propia.
3. Un solo proceso escribe `data/events.json`; no hay bloqueo entre procesos.
4. El estado de LocalStack es efímero: `docker compose down` lo borra.
5. La notificación puede duplicarse si el worker muere después del envío y antes
   de guardar el resultado.
6. La ventana HMAC no impide repeticiones dentro de los 300 s.
7. `python-dotenv` no sobrescribe variables ya exportadas en la terminal.
8. HMAC no sustituye TLS, límites de tasa ni control de acceso de red. En una
   exposición pública se requiere un proxy que termine TLS, aplique el límite
   de tamaño antes de Uvicorn, rate limiting y, si el emisor lo permite, una
   lista de redes origen.
9. El secreto compartido no tiene rotación ni identificador de clave. Una
   integración real debe admitir rotación con dos claves durante la transición,
   almacenarlas fuera de `.env` y revocar de inmediato ante exposición.

## 9. Correcciones conceptuales (material de defensa)

| Error común | Lo correcto |
|---|---|
| “HMAC garantiza no repudio” | Da autenticación e integridad entre quienes comparten el secreto; no demuestra autoría exclusiva |
| “Firmar el timestamp impide replay” | Solo rechaza entregas viejas; dentro de la ventana puede repetirse |
| “`t=...,v1=...` es un estándar” | Es el contrato elegido, inspirado en Stripe; GitHub usa otro |
| “Tipo + timestamp sirve como idempotencia” | Usar `event_id` estable; el timestamp cambia al reintentar |
| “Los webhooks garantizan al menos una vez” | Depende del proveedor, retención y límites |
| “Consultar caché evita duplicados” | GET + SET no es atómico: hay carreras |
| “Un timeout fija la duración total” | En `requests` se controlan conexión y lectura por separado |
| “Responder 200 y después guardar” | Primero guardar durable, después 2xx |
| “`compare_digest` tarda siempre igual” | Evita cortocircuito por contenido; no es garantía absoluta |
| “El worker confirma al recibir” | Confirma (ACK) solo después de reparar, notificar y persistir |

## 10. Referencias del curso

- Lab-1: Inicialización de SDKs Cloud, Emulación con LocalStack y Autenticación
  Segura.
- Gestión de Estado, Redes Cloud (VPCs, Security Groups).
- Laboratorio 1: Detección y Remediación de Drift con Boto3 y LocalStack.
- Arquitecturas Orientadas a Eventos (EDA) y Comunicación Asíncrona en Python.
- Webhooks en Python: Arquitectura, Seguridad (HMAC) e Idempotencia.
- Emisión Automática de Alertas y Soluciones Desatendidas con Python.
