# F12 — Reinicio después de reparar: solo queda el aviso

- **Fecha:** 2026-11-14
- **Responsable:** I6 — Gaspar, Lautaro Miguel Angel
- **Rama / commit:** `rol6-tests` / commit que acompaña este archivo
- **Entorno:** Python 3.14 · LocalStack 3.8.0 · Docker Compose

## Preparación

El test usa `tmp_path` y fakes: no necesita LocalStack ni tocar `data/` del
grupo.

```bash
source .venv/bin/activate
export PYTHONPATH=src
```

## Comando

```bash
pytest tests/test_scenarios.py::test_restart_after_repair_only_notifies -v
```

## Resultado esperado

Si el ledger ya tiene `repair_done=True` y `notified=False`, el reinicio envía
solo el aviso pendiente y no repite la reparación.

## Resultado obtenido

```text
============================= test session starts ==============================
collecting ... collected 1 item

tests/test_scenarios.py::test_restart_after_repair_only_notifies PASSED  [100%]

============================== 1 passed in 0.07s ===============================
```

## Qué verifica el test

- Prepara un ledger con el evento `evt-001` en estado `repaired`,
  `repair_done=True`, `notified=False`.
- Ejecuta `remediation.handle(EVENT)`, que simula el reinicio del worker.
- Verifica que `repair` **no se llamó** y que `notify` se llamó una vez.
- Verifica que el registro queda `notified=True` y `status="done"`.

## Observaciones

- El caso cubre el corte entre reparación y aviso: la reparación ya es durable,
  el aviso todavía no.
- No hay transacción entre el ledger y Telegram/Slack; por eso el reintento se
  concentra en el aviso y no vuelve a tocar el recurso.
- Salida de referencia capturada sobre el commit `3157626`. Si tu corrida
  difiere en tiempos o plataforma, reemplazá el bloque por tu salida.
