# F08 — JSON corrupto inyectado directo a SQS

- **Fecha:** 2026-11-14
- **Responsable:** I6 — Gaspar, Lautaro Miguel Angel
- **Rama / commit:** `rol6-tests` / commit que acompaña este archivo
- **Entorno:** Python 3.14 · LocalStack 3.8.0 · Docker Compose

## Preparación

```bash
docker compose up -d
# esperar a que LocalStack esté healthy
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
```

## Comando

```bash
pytest tests/test_scenarios.py::test_redrive_with_localstack -v
```

## Resultado esperado

El mensaje corrupto no se procesa, no tumba al worker y termina en la DLQ con
el `Body` intacto.

## Resultado obtenido

```text
============================= test session starts ==============================
collecting ... collected 1 item

tests/test_scenarios.py::test_redrive_with_localstack PASSED             [100%]

============================== 1 passed in 19.28s ==============================
```

## Qué verifica el test

- Publica literalmente `{esto no es json` en la cola de trabajo.
- Consume con el worker hasta que SQS deriva el mensaje a la DLQ
  (`maxReceiveCount=3` de `ensure_queues`).
- Compara `mensaje["Body"] == "{esto no es json"`: el cuerpo llegó sin
  alteraciones.
- Ejecuta otra vez `worker.run(..., once=True)` con la cola vacía para comprobar
  que el worker sigue vivo.
- Verifica que se registró el evento `mensaje_reintentable`.

## Observaciones

- Las colas efímeras se borran en `finally`; por eso la evidencia es la salida
  del test y no una captura posterior de la consola de SQS.
- La lectura manual de una DLQ real, con colas propias y sin borrar antes de
  documentar, está en `evidence/F10-lectura-dlq.md` (I2).
- Salida de referencia capturada sobre el commit `3157626`. Si tu corrida
  difiere en tiempos o plataforma, reemplazá el bloque por tu salida.
