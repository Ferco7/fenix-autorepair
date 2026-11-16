# F11 — Evento duplicado e idempotencia

- **Fecha:** 2026-11-14
- **Responsable:** I6 — Gaspar, Lautaro Miguel Angel
- **Rama / commit:** `rol6-tests` / commit que acompaña este archivo
- **Entorno:** Python 3.14 · LocalStack 3.8.0 · Docker Compose

## Preparación

Los dos tests usan fakes y `tmp_path`: no necesitan LocalStack ni tocar `data/`
del grupo. Alcanza con tener el entorno instalado:

```bash
source .venv/bin/activate
export PYTHONPATH=src
```

## Comando

```bash
pytest tests/test_scenarios.py::test_duplicate_is_idempotent \
       tests/test_scenarios.py::test_ack_is_after_success -v
```

## Resultado esperado

Repetir el mismo evento no vuelve a reparar ni a avisar, y un fallo nunca se
confirma.

## Resultado obtenido

```text
============================= test session starts ==============================
collecting ... collected 2 items

tests/test_scenarios.py::test_duplicate_is_idempotent PASSED             [ 50%]
tests/test_scenarios.py::test_ack_is_after_success PASSED                [100%]

============================== 2 passed in 0.07s ===============================
```

## Qué verifica cada test

**`test_duplicate_is_idempotent`**

- Ejecuta `remediation.handle(EVENT)` dos veces: la segunda relee el ledger,
  como después de un reinicio del worker.
- Cuenta las llamadas: `repair == 1` y `notify == 1`.
- El registro del ledger no cambia entre la primera y la segunda ejecución.
- Queda `repair_done=True`, `notified=True` y `status="done"`.

**`test_ack_is_after_success`**

- Con un handler que lanza `RetryableError`, el orden es
  `handler → retry`: **nunca** se llama a `acknowledge`.
- Con un handler que termina bien, el orden es `handler → ack`: el ACK ocurre
  después del éxito.

## Observaciones

- Son pruebas unitarias con `monkeypatch`; no consumen SQS real.
- La evidencia de la DLQ real está en F08/F10 y en la lectura manual de I2.
- Salida de referencia capturada sobre el commit `3157626`. Si tu corrida
  difiere en tiempos o plataforma, reemplazá el bloque por tu salida.
