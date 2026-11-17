# F16 — Rotación de logs y lectura del histórico gzip

- **Fecha:** 2026-11-17
- **Responsable:** I4 — Alegre, Facundo Sebastián
- **Módulo:** `src/fenix/utils/logging_json.py`
- **Base:** `main` = `9ce3fd9` · PR #20

## Comando

```bash
pytest tests/test_i4_observabilidad.py::test_rotacion_gzip_comprime_y_borra -v
```

## Resultado obtenido

```text
collected 1 item

tests/test_i4_observabilidad.py::test_rotacion_gzip_comprime_y_borra PASSED [100%]

============================== 1 passed in 0.10s ===============================
```

## Histórico comprimido

Generación con tamaño reducido para forzar la rotación:

```bash
python - <<'PY'
import logging, logging.handlers
from fenix.utils import logging_json

handler = logging.handlers.RotatingFileHandler(
    "evidence/F16-rotacion.jsonl", maxBytes=1200, backupCount=1, encoding="utf-8")
handler.setFormatter(logging_json.JSONFormatter())
handler.namer, handler.rotator = logging_json.gzip_name, logging_json.gzip_rotate
logger = logging.getLogger("f16")
logger.handlers.clear()
logger.propagate = False
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
for n in range(20):
    logger.info("linea %s", n, extra={"event_id": f"evt-{n}"})
handler.close()
PY
```

Artefacto adjunto:
[`F16-rotacion.jsonl.1.gz`](F16-rotacion.jsonl.1.gz) · 238 bytes · 4 líneas.

Lectura del `.gz`:

```bash
python - <<'PY'
import gzip, json
with gzip.open("evidence/F16-rotacion.jsonl.1.gz", "rt", encoding="utf-8") as f:
    lines = [json.loads(line) for line in f]
print("lineas:", len(lines))
print("niveles:", [l["level"] for l in lines])
print("claves:", sorted(lines[0].keys()))
PY
```

```text
lineas: 4
niveles: ['INFO', 'INFO', 'INFO', 'INFO']
claves: ['action', 'attempt', 'event_id', 'level', 'message', 'message_id', 'process', 'resource_id', 'status', 'thread', 'timestamp']
```

## Observaciones

- `.gitignore` ignora `*.gz`; el adjunto se agregó con `git add -f`.
- El `.jsonl` sin comprimir es estado de runtime y no se versiona.
- Las líneas conservan `timestamp` en UTC y sólo los campos autorizados.
