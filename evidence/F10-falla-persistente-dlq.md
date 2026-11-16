# F10 — Falla persistente y derivación a la DLQ

- **Fecha:** 2026-11-14
- **Responsable:** I6 — Gaspar, Lautaro Miguel Angel
- **Rama / commit:** `rol6-tests` / commit que acompaña este archivo
- **Entorno:** Python 3.14 · LocalStack 3.8.0 · Docker Compose

> Esta evidencia documenta el **test de integración** de F10. La fila F10 de la
> matriz y la lectura manual del mensaje en la DLQ son de I2
> (`evidence/F10-lectura-dlq.md`); este archivo cubre la parte automática.

## Preparación

```bash
docker compose up -d
# esperar a que LocalStack esté healthy
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
```

## Comando

```bash
pytest tests/test_scenarios.py::test_persistent_failure_reaches_dlq -v
```

## Resultado esperado

El mensaje con `simulate_failures=5` nunca se confirma: agota `maxReceiveCount`
y termina en la DLQ con `repair_done=false`.

## Resultado obtenido

```text
============================= test session starts ==============================
collecting ... collected 1 item

tests/test_scenarios.py::test_persistent_failure_reaches_dlq PASSED      [100%]

============================== 1 passed in 9.28s ===============================
```

## Qué verifica el test

- Publica un evento con `event_id="evt-f10"` y `simulate_failures=5`.
- Consume con `remediation.handle` hasta que el mensaje aparece en la DLQ.
- Verifica que **nunca se hizo ACK**: `acks == []`.
- Verifica que el `Body` en la DLQ conserva `event_id == "evt-f10"`.
- Verifica el ledger: `attempts >= 3` y `repair_done is False`.

## Observaciones

- `retry_later` se reemplaza por una versión con visibilidad de 1 segundo para
  acortar la espera del test; la política de redrive es la real.
- Las colas se eliminan en `finally`, después de las aserciones.
- Salida de referencia capturada sobre el commit `3157626`. Si tu corrida
  difiere en tiempos o plataforma, reemplazá el bloque por tu salida.
