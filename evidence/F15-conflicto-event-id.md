# F15 — Reutilización de `event_id` con otro contenido

- **Fecha:** 2026-11-16
- **Responsable:** I5 — Rodríguez, Hector Fernando
- **Rama / commit:** `rol5-worker` / commit que acompaña este
- **Entorno:** Windows · Python 3.14.5 · pytest 9.2.0

## Preparación

La prueba usa `tmp_path` y mocks; no necesita LocalStack ni modifica los datos
del proyecto.

## Comando

```
pytest tests/test_i5_worker.py::test_handle_registra_conflicto_sin_cambiar_el_original -v
```

## Resultado esperado

Al procesar un evento y luego reutilizar su `event_id` con otro contenido:

- se registra el evento conflictivo en `_conflicts`;
- el registro original del ledger queda sin cambios;
- no se repiten la reparación ni la notificación.

## Resultado obtenido

```text
============================= test session starts =============================
collecting ... collected 1 item

tests/test_i5_worker.py::test_handle_registra_conflicto_sin_cambiar_el_original PASSED [100%]

============================== 1 passed in 2.71s ==============================
```

## Evidencia

El test verifica que reutilizar un `event_id` con contenido distinto genera un conflicto en `_conflicts`, conserva intacto el registro original y no repite la reparación ni la notificación.

## Observaciones

Es una prueba unitaria de `remediation.handle`: verifica el conflicto en el
ledger y que no se repitan la reparación ni la notificación. No prueba el ACK
de SQS ni un flujo real con LocalStack.
