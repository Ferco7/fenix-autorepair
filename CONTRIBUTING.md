# Contribuir — Proyecto Fénix

## 1. Preparar el entorno

Seguir `docs/ENTORNO.md`. Resumen:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"  # -> WEBHOOK_SECRET
python scripts/doctor.py
```

## 2. Ramas

Repositorio: **`fenix-autorepair`**. `main` queda estable. Cada integrante trabaja **solo** en su rama y mergea por pull request.

| Rol | Rama |
|---|---|
| I1 | `rol1-entradas` |
| I2 | `rol2-mensajeria` |
| I3 | `rol3-webhooks` |
| I4 | `rol4-observabilidad` |
| I5 | `rol5-worker` |
| I6 | `rol6-tests` |

`main` queda estable. Cada integrante trabaja **solo** en su rama y mergea por
pull request.

## 3. Commits

Formato: `rol N: descripción corta` para el trabajo del rol. Para el resto:

- `test: ...`
- `docs: ...`
- `fix: ...`
- `chore: ...`

Ejemplos:

```
rol 2: implementar ensure_queues y retry_later
test: cubrir redrive real contra LocalStack
docs: completar matriz F01-F16
```

Un commit = un cambio coherente. No mezclar refactors con features.

## 4. Pull request

1. Actualizar `main` y rebasar la rama.
2. Correr `pytest -m base -q` y las pruebas del rol.
3. Abrir el PR con la plantilla `.github/pull_request_template.md`.
4. Pedir revisión cruzada (ver `docs/ROLES.md`).
5. Mergear solo con la aprobación y el CI en verde.

## 5. Reglas de código

- Sin `except: pass`, sin `BaseException`, sin `return`/`break`/`continue` en
  `finally`.
- Toda llamada de red con timeout de conexión y lectura.
- Errores del dominio: `ValidationError`, `RetryableError`, `PermanentError`.
- No imprimir secretos, tokens, URLs privadas ni el cuerpo crudo del webhook.
- No agregar dependencias sin actualizar `requirements.txt` y el lock.
- No modificar archivos de otro rol ni los archivos congelados sin acuerdo.

## 6. Alcance

Cada rol toca solo sus archivos (ver `docs/ROLES.md`). Si un cambio cruza roles,
se acuerda en el PR y se documenta.

## 7. Documentación y evidencia

- Actualizar la sección del README que corresponda.
- Registrar la evidencia F en `evidence/` con fecha, comando y resultado.
- Capturas en `docs/images/`, sin secretos.
- Si se toma una decisión nueva, agregarla a `docs/DECISIONES.md`.

## 8. Antes de pedir revisión

```bash
pytest -m base -q
pytest -m pendiente -q      # debe reflejar el avance real
python scripts/doctor.py
```

- [ ] Sin `.env`, `.venv/`, `data/`, `logs/` ni tokens en el diff.
- [ ] Sin `NotImplementedError` en las funciones del rol.
- [ ] Docstrings actualizados.
- [ ] Evidencia cargada.
