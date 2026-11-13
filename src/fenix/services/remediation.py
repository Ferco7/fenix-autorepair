"""Acciones convergentes a completar por integrante 3 y coordinadas por 5."""
from botocore.exceptions import BotoCoreError, ClientError
from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.services.events import validate
from fenix.services.notifications import notify
from fenix.utils.errors import RetryableError, PermanentError


TRANSIENT_CODES = {
    "InternalError", "InternalFailure", "RequestLimitExceeded", "RequestTimeout",
    "ServiceUnavailable", "SlowDown", "ThrottledException", "Throttling",
    "ThrottlingException",
}


def _raise_classified(error: ClientError) -> None:
    """Convierte errores de AWS en reintentos o fallos permanentes sin filtrarlos."""
    details = error.response.get("Error", {})
    code = details.get("Code", "")
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
    if code in TRANSIENT_CODES or isinstance(status, int) and status >= 500:
        raise RetryableError("El servicio cloud no está disponible") from None
    raise PermanentError("El recurso cloud no puede repararse") from None


def _instance_state(ec2, instance_id: str) -> str:
    """Obtiene exactamente el estado del único recurso autorizado."""
    response = ec2.describe_instances(InstanceIds=[instance_id])
    instances = [instance for reservation in response.get("Reservations", [])
                 for instance in reservation.get("Instances", [])]
    if len(instances) != 1:
        raise PermanentError("La instancia autorizada no existe")
    state = instances[0].get("State", {}).get("Name")
    if not isinstance(state, str):
        raise PermanentError("La instancia autorizada no tiene un estado válido")
    return state


def _bucket_tags(s3, bucket_id: str) -> dict[str, str]:
    """Lee etiquetas S3; solamente NoSuchTagSet representa un conjunto vacío."""
    try:
        tag_set = s3.get_bucket_tagging(Bucket=bucket_id).get("TagSet", [])
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "NoSuchTagSet":
            return {}
        _raise_classified(error)
    tags: dict[str, str] = {}
    for tag in tag_set:
        key, value = tag.get("Key"), tag.get("Value")
        if not isinstance(key, str) or not isinstance(value, str) or key in tags:
            raise PermanentError("Las etiquetas del bucket no tienen un formato válido")
        tags[key] = value
    return tags


def _required_tags(resource: dict) -> dict[str, str]:
    """Valida que el inventario entregue una política de etiquetas escribible."""
    tags = resource.get("tags")
    if (not isinstance(tags, dict) or not tags
            or any(not isinstance(key, str) or not isinstance(value, str)
                   for key, value in tags.items())):
        raise PermanentError("El inventario no define etiquetas válidas")
    return dict(tags)


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
    Side Effects:
        Arranca una instancia EC2 mock detenida o restaura tags de un bucket S3.
    Notes:
        No usar reboot_instances: repetir un reinicio no es convergencia.
        Un estado pending requiere otra recepción, sin esperas largas en el worker.
    """
    if not isinstance(resource, dict):
        raise PermanentError("El recurso del inventario no es válido")
    resource_id = resource.get("id")
    if not isinstance(resource_id, str) or not resource_id:
        raise PermanentError("El recurso del inventario no tiene un ID válido")

    if event_type == "instance.stopped":
        if resource.get("type") != "ec2":
            raise PermanentError("El evento no corresponde al recurso autorizado")
        try:
            ec2 = client("ec2")
            state = _instance_state(ec2, resource_id)
            if state == "running":
                return "already_ok"
            if state == "pending":
                raise RetryableError("La instancia todavía está iniciando")
            if state in {"stopping", "terminated", "shutting-down"}:
                raise PermanentError("La instancia no puede iniciarse")
            if state != "stopped":
                raise PermanentError("La instancia tiene un estado no permitido")

            ec2.start_instances(InstanceIds=[resource_id])
            if _instance_state(ec2, resource_id) != "running":
                raise RetryableError("La instancia aún no está en ejecución")
            return "repaired"
        except ClientError as error:
            _raise_classified(error)
        except BotoCoreError:
            raise RetryableError("El servicio cloud no está disponible") from None

    if event_type == "bucket.tags_missing":
        if resource.get("type") != "s3":
            raise PermanentError("El evento no corresponde al recurso autorizado")
        required = _required_tags(resource)
        try:
            s3 = client("s3")
            current = _bucket_tags(s3, resource_id)
            desired = {**current, **required}  # Conserva todas las etiquetas ajenas.
            if current == desired:
                return "already_ok"
            s3.put_bucket_tagging(Bucket=resource_id, Tagging={
                "TagSet": [{"Key": key, "Value": value}
                           for key, value in desired.items()]})
            stored = _bucket_tags(s3, resource_id)
            if stored != desired:
                raise RetryableError("Las etiquetas aún no se pueden verificar")
            return "repaired"
        except ClientError as error:
            _raise_classified(error)
        except BotoCoreError:
            raise RetryableError("El servicio cloud no está disponible") from None

    raise PermanentError("El tipo de evento no está permitido")


def handle(event: dict) -> None:
    """Completa reparación y notificación usando un registro durable por evento.

    Args:
        event: Objeto recibido de SQS, que se vuelve a validar aquí.
    Returns:
        None solo cuando reparación y aviso quedaron registrados como exitosos.
    Raises:
        ValidationError: Si el evento fue inyectado directamente a SQS y no es válido.
        RetryableError: Si la simulación o una dependencia temporal falla.
        PermanentError: Conflicto de event_id o recurso no autorizado.
        NotImplementedError: Mientras falte TODO I5-B.
    Side Effects:
        Actualiza recursos, data/events.json y el canal de comunicación.
    Notes:
        Un solo proceso modifica el ledger. Un timeout al notificar puede repetir
        un aviso: no existe una transacción común entre JSON, AWS y Telegram/Slack.
    """
    # TODO I5-B: cargar inventario y validar; cargar ledger por event_id.
    # Vincular event_id al contenido del evento; rechazar reutilización con otro contenido.
    # Guardar attempts incrementado antes de simular fallas; persiste entre reinicios.
    # Si attempts <= simulate_failures, lanzar RetryableError sin modificar recursos.
    # Si repair_done es falso: repair; guardar resultado y repair_done=True.
    # Si notified es falso: notify resumen; guardar notified=True después del éxito.
    # Si ambas etapas ya estaban completas, retornar sin efectos repetidos.
    # Cada save debe preservar el resto del ledger; no sobrescribir otros eventos.
    raise NotImplementedError("I5-B: integrar etapas y ledger durable")
