"""Acciones convergentes a completar por integrante 3 y coordinadas por 5."""
import json 
from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.services.events import validate
from fenix.services.notifications import notify
from fenix.utils.errors import RetryableError, PermanentError

INVENTORY_PATH = "data/inventory.json"
LEDGER_PATH = "data/events.json"


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
    """Completa reparación y notificación usando un registro durable por evento."""
    inventory = load(INVENTORY_PATH)
    validated = validate(event, inventory)
    event_id = validated["event_id"]
    content = json.dumps(validated, sort_keys=True, ensure_ascii=False)

    ledger = load(LEDGER_PATH)  
    record = ledger.get(event_id)  
    
    if record is not None:  
        if record.get("content") != content:  
            raise PermanentError("event_id reutilizado con otro contenido")  
        if record.get("repair_done") and record.get("notified"):  
            return  # Nada pendiente: no repetir acciones ya verificadas.  
    else:  
        record = {"content": content, "attempts": 0,  
                  "repair_done": False, "notified": False}  
        ledger[event_id] = record  

    record["attempts"] += 1  
    save(LEDGER_PATH, ledger)  

    if record["attempts"] <= validated["simulate_failures"]:  
        raise RetryableError("Falla simulada pendiente de reintento")  

    resource = inventory[validated["resource_id"]]  

    if not record.get("repair_done"):  
        record["result"] = repair(resource, validated["event_type"])  
        record["repair_done"] = True  
        save(LEDGER_PATH, ledger)  

    if not record.get("notified"):  
        notify(f"Evento {event_id}: {validated['event_type']} en "  
               f"{validated['resource_id']} -> {record.get('result', 'sin cambios')}")  
        record["notified"] = True  
        save(LEDGER_PATH, ledger)
