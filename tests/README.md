# Pruebas — Proyecto Fénix

## Estado actual

| Suite | Marca | Estado |
|---|---|---|
| `tests/test_base.py` | `base` | **4/4 verdes** (apoyo del template) |
| `tests/test_contracts.py` | `pendiente` | 3 fallan hasta completar I1 |
| `tests/test_fenix.py` | `pendiente` | 1 falla hasta completar I3 |
| `tests/test_scenarios.py` | `pendiente` / `integracion` | 2 + 1 fallan hasta I5/I6 |

## Comandos

```bash
pytest -m base -q          # debe quedar verde siempre
pytest -m pendiente -q     # contratos del equipo
pytest -m integracion -q   # requiere LocalStack arriba
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
| I6 | suite completa | matriz F01–F16 y redrive real contra LocalStack |
