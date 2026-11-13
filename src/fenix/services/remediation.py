"""Acciones convergentes a completar por integrante 3 y coordinadas por 5."""
import json  #vincula cada event_id con el contenido exacto recibido
from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.services.events import validate
from fenix.services.notifications import notify
from fenix.utils.errors import RetryableError, PermanentError

INVENTORY_PATH = "data/inventory.json" #Ruta compartida con receptor y worker.
LEDGER_PATH = "data/events.json" #Estado durable por event_id.


def repair(resource: dict, event_type: str) -> str:
    """Acerca un recurso autorizado a su estado deseado y verifica el resultado.

    Args:
        resource: Registro de inventario con type/id y etiquetas esperadas.
        event_type: instance.stopped o bucket.tags_missing ya validado.
    Returns:
        "repaired" si cambió el estado; "already_ok" si ya cumplía la política.
    Raises:
        RetryableError: La API falla temporalmente o el estado final aún no se observa.
        PermanentError: Recurso inexistente o configuración no autorizada.
        NotImplementedError: Mientras no se complete TODO I3-C.
    Side Effects:
        Arranca una instancia EC2 mock detenida o restaura tags de un bucket S3.
    Notes:
        No usar reboot_instances: repetir un reinicio no es convergencia.
        Un estado pending requiere otra recepción, sin esperas largas en el worker.
    """
    # TODO I3-C EC2: describe_instances por el InstanceId leído del inventario.
    # running -> already_ok; stopped -> start_instances; pending -> RetryableError.
    # Volver a consultar y exigir running; stopping/terminated -> error explicado.
    # TODO I3-C S3: get_bucket_tagging; solo NoSuchTagSet equivale a tags vacías.
    # Combinar tags actuales con obligatorias; put_bucket_tagging si hay desvío.
    # Volver a leer tags; preservar etiquetas ajenas a la política.
    # Clasificar ClientError por código: throttling/5xx transitorio, no todo ClientError.
    raise NotImplementedError("I3-C: implementar remediación convergente")


def handle(event: dict) -> None:
    """Completa reparación y notificación usando un registro durable por evento.

    Args:
        event: Objeto recibido de SQS, que se vuelve a validar aquí.
    Returns:
        None solo cuando reparación y aviso quedaron registrados como exitosos.
    Raises:
        ValidationError: Si el evento inyectado no es válido.
        RetryableError: Si la simulación o una dependencia temporal falla.
        PermanentError: Conflicto de event_id o recurso no autorizado.
        NotImplementedError: Mientras falte TODO I3-C o I4-A.
    Side Effects:
        Actualiza recursos, data/events.json y el canal de comunicación.
    Notes:
        Un solo proceso modifica el ledger. Un timeout al notificar puede repetir
        un aviso: no existe una transacción común entre JSON, AWS y Telegram/Slack.
    """
    inventory = load(INVENTORY_PATH)
    validated = validate(event, inventory)  # Revalida aunque venga de SQS.
    event_id = validated["event_id"]
    content = json.dumps(validated, sort_keys=True, ensure_ascii=False)

    ledger = load(LEDGER_PATH)
    record = ledger.get(event_id)

    if record is not None:
        if record.get("content") != content:
            raise PermanentError("event_id reutilizado con otro contenido")
        if record.get("repair_done") and record.get("notified"):
            if record.get("status") != "done":  # Completa un ledger viejo.
                record["status"] = "done"
                save(LEDGER_PATH, ledger)
            return  # Nada pendiente: no repetir acciones ya verificadas.
    else:
        record = {
            "content": content,
            "attempts": 0,
            "repair_done": False,
            "repair_result": None,
            "notified": False,
            "status": "pending",
        }
        ledger[event_id] = record

    record["attempts"] = int(record.get("attempts", 0)) + 1
    record["status"] = "retrying"
    save(LEDGER_PATH, ledger)  # attempts durable antes de cualquier efecto.

    if record["attempts"] <= validated["simulate_failures"]:
        raise RetryableError("Falla simulada pendiente de reintento")

    resource = inventory[validated["resource_id"]]

    if not record.get("repair_done"):
        record["repair_result"] = repair(resource, validated["event_type"])
        record["repair_done"] = True
        record["status"] = "repaired"
        save(LEDGER_PATH, ledger)  # Reparación durable antes de notificar.

    if not record.get("notified"):
        notify(
            f"Evento {event_id}: {validated['event_type']} en "
            f"{validated['resource_id']} -> "
            f"{record.get('repair_result', 'sin cambios')}"
        )
        record["notified"] = True
        record["status"] = "done"
        save(LEDGER_PATH, ledger)

    record["status"] = "done"
    save(LEDGER_PATH, ledger)