# Evidencias — Proyecto Fénix

Esta carpeta guarda la evidencia reproducible de la matriz **F01–F16** del
README. Una carpeta llena de capturas sin comando no sirve: cada archivo debe
permitir que otra persona repita la prueba.

## Convención de nombres

```
evidence/F01-init-queues-idempotente.md
evidence/F02-nodo-detenido-reparado.md
...
evidence/F16-rotacion-logs.md
```

Las capturas van en `docs/images/` y se referencian desde el `.md` y desde el
README.

## Plantilla

```markdown
# F01 — init-queues / setup-demo idempotente

- **Fecha:** 2026-11-11
- **Responsable:** I2 — Maldonado, Fernando Manuel
- **Rama / commit:** rol2-mensajeria / abc1234
- **Entorno:** Python 3.14.4 · LocalStack 3.8.0 · Docker 29.1.3

## Preparación

```bash
docker compose up -d
python scripts/doctor.py
```

## Comando

```bash
python -m fenix.cli init-queues
python -m fenix.cli init-queues
python -m fenix.cli setup-demo
python -m fenix.cli setup-demo
```

## Resultado esperado

Mismas URLs, mismos IDs de inventario, sin duplicados.

## Resultado obtenido

(pegar salida real, sin secretos)

## Evidencia

- Captura: `docs/images/F01-init-queues.png`
- Log: `logs/fenix-init-queues-<pid>.jsonl`

## Observaciones

(limitaciones, diferencias con lo esperado, próximos pasos)
```

## Reglas

1. **Sin secretos:** ocultar tokens, chat IDs, URLs privadas y cuerpos crudos.
2. **Sin rutas absolutas personales:** usar rutas relativas al proyecto.
3. **Comando + salida:** no alcanza con “funcionó”.
4. **Fecha y responsable:** obligatorios.
5. **Entorno:** indicar versión de Python, imagen de LocalStack y commit.
6. **No inventar evidencia:** si una prueba no se corrió, queda pendiente.

## Matriz rápida

| ID | Evidencia principal |
|---|---|
| F01 | Salida de `init-queues` y `setup-demo` repetidos |
| F02 | `describe-instances` en `running` + ledger completo |
| F03 | `get_bucket_tagging` con las cuatro etiquetas |
| F04 | Respuestas 401 (firma ausente/alterada/vieja) |
| F05 | 401 por bytes distintos tras firmar |
| F06 | 400 (JSON roto) y 422 (lista) |
| F07 | 422 por alias ajeno y claves extra |
| F08 | Mensaje corrupto en SQS -> DLQ, worker vivo |
| F09 | `simulate_failures=2` con backoff 2 y 4 |
| F10 | Falla persistente sin ACK -> DLQ |
| F11 | Evento repetido / worker reiniciado sin repetir acciones |
| F12 | Corte tras `repair_done`; reinicio solo notifica |
| F13 | 503 con SQS detenido |
| F14 | 429/timeout y luego éxito; no repite reparación |
| F15 | Mismo `event_id` con otro payload -> conflicto |
| F16 | Log rotado `.gz` leído y parseado como JSON |
