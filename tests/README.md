# Pruebas — Proyecto Fénix

## Estado actual

Con LocalStack arriba, `pytest -q` deja **108 passed**.

| Suite | Marca | Casos |
|---|---|---|
| `tests/test_base.py` | `base` | 4 |
| `tests/test_contracts.py` | unitarios | 3 |
| `tests/test_fenix.py` | unitarios | 1 |
| `tests/test_i1_entradas.py` | unitarios | 21 |
| `tests/test_i2_mensajeria.py` | unitarios + 2 de integración | 11 |
| `tests/test_i3_webhooks.py` | unitarios | 11 |
| `tests/test_i4_observabilidad.py` | unitarios | 29 |
| `tests/test_i5_worker.py` | unitarios | 13 |
| `tests/test_i6_diagnostico.py` | unitarios con fakes | 10 |
| `tests/test_scenarios.py` | 3 unitarios + 2 de integración | 5 |

Las suites `test_contracts.py` y `test_fenix.py` ya no llevan la marca
`pendiente`: están implementadas y pasan. La marca sigue definida en
`pyproject.toml` para futuras plantillas, pero hoy no selecciona casos.

`tests/test_i6_diagnostico.py` cubre `inject_fault`: alias desconocido, tipo
incorrecto, instancia ya terminada, límite de consultas, y las variantes de
`bucket-01` (quitar `Owner`, idempotencia, grupo ajeno, bucket sin tags y
recuperación de un bucket creado sin etiquetas).

### Correcciones cubiertas por la suite

- `test_i4_observabilidad.py::test_errores_de_red_son_reintentables`: timeout,
  conexión y otras `RequestException` se traducen a `RetryableError`.
- `test_i4_observabilidad.py::test_niveles_debug_y_critical_se_serializan`: los
  cinco niveles se escriben como JSON con timestamp UTC.
- `test_i2_mensajeria.py::test_retry_later_tolera_contador_malformado`: un
  `ApproximateReceiveCount` inválido no tumba el worker.
- `test_i2_mensajeria.py::test_setup_demo_rechaza_inventario_que_no_es_objeto`:
  un JSON con forma de lista se rechaza con `PermanentError`.
- `test_i6_diagnostico.py::test_bucket_creado_sin_tags_se_recupera`: una
  segunda corrida completa las etiquetas sin crear otro bucket.

`tests/test_scenarios.py` cubre F08, F10, F11 y F12:

| Test | Caso |
|---|---|
| `test_duplicate_is_idempotent` | F11: repetir el evento no repara ni avisa de nuevo |
| `test_ack_is_after_success` | F11/F12: un fallo no confirma; el éxito confirma al final |
| `test_restart_after_repair_only_notifies` | F12: reinicio con `repair_done` solo notifica |
| `test_redrive_with_localstack` | F08: JSON corrupto llega a la DLQ real |
| `test_persistent_failure_reaches_dlq` | F10: falla persistente agota `maxReceiveCount` |

Los dos últimos llevan la marca `integracion` y necesitan LocalStack; los otros
tres usan fakes y corren sin red.

## Comandos

```bash
pytest -m base -q          # debe quedar verde siempre
pytest -m pendiente -q     # sin casos: la marca queda para futuras plantillas
pytest -m integracion -q   # requiere LocalStack arriba
pytest -m "not integracion" -q  # todo lo que no necesita red
pytest -q                  # todo
```

## Reglas

1. **No se borran** los tests del template: se completan.
2. Cada rol agrega sus pruebas en su rama y las defiende en la exposición.
3. Los tests unitarios no dependen de red: se usan fakes, `monkeypatch` o
   `botocore.stub.Stubber`.
4. Los tests de integración usan LocalStack real y un prefijo único; limpian sus
   recursos al finalizar.
5. Nunca se commitean capturas con tokens, chat IDs ni cuerpos con secretos.
6. Para probar rotación de logs, borrar el archivo previo o usar un `tmp_path`:
   `RotatingFileHandler` abre en modo append.
7. Un test que depende de otro rol debe usar un fake, no esperar a que el otro
   termine.

## Responsables

- **I6** custodia la suite completa, `conftest.py` y la matriz F01–F16.
- Cada rol escribe y defiende las pruebas de su módulo.
- La revisión cruzada se registra en el PR (ver `docs/ROLES.md`).

## Cobertura esperada por rol

| Rol | Archivo sugerido | Qué debe demostrar |
|---|---|---|
| I1 | `test_i1_entradas.py` | rechazos de identificadores, TTL, UTC y esquema cerrado |
| I2 | `test_i2_mensajeria.py` | colas idempotentes, DLQ, backoff, inventario |
| I3 | `test_i3_webhooks.py` | 401/413/400/422/503/202 y reparación convergente |
| I4 | `test_i4_observabilidad.py` | 429/timeout/5xx, `Retry-After`, JSON de logs |
| I5 | `test_i5_worker.py` | ACK después del éxito, reintentos, ledger durable |
| I6 | `test_i6_diagnostico.py` + `test_scenarios.py` | `inject_fault` con fakes y escenarios F08/F10/F11/F12, incluido el redrive real |
