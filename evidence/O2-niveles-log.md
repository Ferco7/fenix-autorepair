# O2 — Los cinco niveles de log se serializan en JSON

- **Fecha:** 2026-11-17
- **Responsable:** I4 — Alegre, Facundo Sebastián
- **Rama / commit:** `fix/tandas-0-3` / commit que acompaña este archivo
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3 · Linux x86_64

## Comando

```bash
python - <<'PY'
from pathlib import Path
from fenix.utils import logging_json

logger, listener = logging_json.setup("fenix-o2")
try:
    logger.debug("decision interna", extra={"event_id": "evt-dbg", "status": "already_ok"})
    logger.info("paso nominal", extra={"event_id": "evt-inf", "status": "done"})
    logger.warning("reintento", extra={"event_id": "evt-warn", "attempt": 1, "status": "retrying"})
    logger.error("fallo temporal", extra={"event_id": "evt-err", "attempt": 2, "status": "retry"})
    logger.critical("configuracion invalida", extra={"status": "fatal"})
finally:
    listener.stop()

for path in Path("logs").glob("*.jsonl"):
    for line in path.read_text(encoding="utf-8").splitlines():
        print(line)
PY
```

## Resultado obtenido

```json
{"timestamp": "2026-11-17T16:12:57.027735+00:00", "level": "DEBUG", "message": "decision interna", "process": 24820, "thread": "MainThread", "event_id": "evt-dbg", "message_id": null, "resource_id": null, "attempt": null, "action": null, "status": "already_ok"}
{"timestamp": "2026-11-17T16:12:57.027799+00:00", "level": "INFO", "message": "paso nominal", "process": 24820, "thread": "MainThread", "event_id": "evt-inf", "message_id": null, "resource_id": null, "attempt": null, "action": null, "status": "done"}
{"timestamp": "2026-11-17T16:12:57.027829+00:00", "level": "WARNING", "message": "reintento", "process": 24820, "thread": "MainThread", "event_id": "evt-warn", "message_id": null, "resource_id": null, "attempt": 1, "action": null, "status": "retrying"}
{"timestamp": "2026-11-17T16:12:57.027847+00:00", "level": "ERROR", "message": "fallo temporal", "process": 24820, "thread": "MainThread", "event_id": "evt-err", "message_id": null, "resource_id": null, "attempt": 2, "action": null, "status": "retry"}
{"timestamp": "2026-11-17T16:12:57.027859+00:00", "level": "CRITICAL", "message": "configuracion invalida", "process": 24820, "thread": "MainThread", "event_id": null, "message_id": null, "resource_id": null, "attempt": null, "action": null, "status": "fatal"}
```

## Qué verifica

Que el formatter conserva los cinco niveles exigidos por la consigna y que los
campos no aplicables se representan como `null`. El nivel `CRITICAL` se usa en
esta fixture solo para demostrar el contrato del logger; los fallos normales del
worker siguen registrándose como `ERROR` o `WARNING`.
