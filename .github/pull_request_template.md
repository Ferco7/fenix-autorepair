## Rol

- [ ] I1 — Entradas y excepciones
- [ ] I2 — Mensajería e inventario cloud
- [ ] I3 — Webhooks y reparación
- [ ] I4 — Observabilidad y comunicación
- [ ] I5 — Integración y worker
- [ ] I6 — Pruebas y diagnóstico

## Alcance

- Archivos tocados:
- Funciones implementadas:
- Casos F cubiertos:

## Checklist

- [ ] `pytest -m base -q` verde.
- [ ] Pruebas del rol agregadas y pasando.
- [ ] Sin `except: pass`, `BaseException` ni `return/break/continue` en `finally`.
- [ ] Timeouts acotados en toda llamada de red.
- [ ] Sin secretos, `.env`, `.venv/`, `data/`, `logs/` ni tokens en el diff.
- [ ] Docstrings y documentación actualizadas.
- [ ] Evidencia registrada en `evidence/` y capturas en `docs/images/`.

## Revisión cruzada

- Revisor asignado:
- [ ] Aprobado por el revisor.

## Evidencia

(comandos ejecutados y resultado obtenido)
