"""Laboratorio acotado de recursos. Integrante 2 prepara, integrante 6 verifica."""
import os  # Obtiene la región usada por el emulador.
import time  # Acota las consultas de estado tras detener la instancia.
from botocore.exceptions import ClientError  # Distingue etiquetas ausentes.
from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.utils.validation import identifier
from fenix.utils.errors import PermanentError, RetryableError, ValidationError
from fenix.services.cloud_support import (
    aws_tags, create_bucket, create_group, create_instance, mock_inputs,
)

INVENTORY_PATH = "data/inventory.json"  # Ruta compartida con receptor y worker.


def _required_tags(group: str) -> dict[str, str]:
    """Devuelve las cuatro etiquetas obligatorias del laboratorio.

    Args:
        group: Identificador ya validado del grupo.
    Returns:
        Mapa con ManagedBy, Project, GroupId y Owner.
    """
    return {"ManagedBy": "ppa2", "Project": "fenix",
            "GroupId": group, "Owner": group}


def _current_tags(resource: dict) -> dict[str, str]:
    """Convierte la lista de etiquetas del SDK en un mapa simple."""
    return {tag["Key"]: tag["Value"] for tag in resource.get("Tags", [])}


def _apply_missing(ec2, resource_id: str, current: dict[str, str],
                   expected: dict[str, str]) -> None:
    """Agrega solo las etiquetas que faltan o difieren de la política."""
    missing = [tag for tag in aws_tags(expected)
               if current.get(tag["Key"]) != tag["Value"]]
    if missing:
        ec2.create_tags(Resources=[resource_id], Tags=missing)


def _ensure_security_group(ec2, group: str, name: str, vpc_id: str,
                           tags: dict[str, str]) -> str:
    """Reutiliza el security group del grupo o lo crea si no existe.

    Args:
        ec2: Cliente EC2 del emulador.
        group: Identificador del grupo dueño del recurso.
        name: Nombre estable del security group.
        vpc_id: VPC predeterminada descubierta por mock_inputs.
        tags: Etiquetas obligatorias que debe tener el recurso.
    Returns:
        GroupId real del emulador.
    Raises:
        PermanentError: Si existe un SG con el mismo nombre pero de otro dueño.
        ClientError: Si EC2 rechaza la consulta o la creación.
    """
    groups = ec2.describe_security_groups(Filters=[
        {"Name": "group-name", "Values": [name]},
        {"Name": "vpc-id", "Values": [vpc_id]},
    ])["SecurityGroups"]
    if not groups:
        return create_group(name, vpc_id, tags)  # Crea con las etiquetas iniciales.
    current = _current_tags(groups[0])
    if (current.get("ManagedBy") not in (None, "ppa2")
            or current.get("Project") not in (None, "fenix")
            or current.get("GroupId") not in (None, group)):
        raise PermanentError("Security group ajeno con el mismo nombre")
    _apply_missing(ec2, groups[0]["GroupId"], current, tags)
    return groups[0]["GroupId"]


def _ensure_instance(ec2, group: str, name: str, image_id: str,
                     security_group_id: str, tags: dict[str, str]) -> str:
    """Reutiliza la instancia del grupo o la crea con ClientToken estable.

    Args:
        ec2: Cliente EC2 del emulador.
        group: Identificador del grupo dueño del recurso.
        name: Valor de la etiqueta Name de la instancia.
        image_id: AMI mock descubierta y guardada en el inventario.
        security_group_id: SG propio ya creado o recuperado.
        tags: Etiquetas obligatorias, incluida Name.
    Returns:
        InstanceId real del emulador.
    Raises:
        PermanentError: Si hay más de una instancia para el mismo grupo.
        ClientError: Si EC2 rechaza la consulta o la creación.
    """
    reservations = ec2.describe_instances(Filters=[
        {"Name": "tag:Project", "Values": ["fenix"]},
        {"Name": "tag:GroupId", "Values": [group]},
        {"Name": "tag:Name", "Values": [name]},
        {"Name": "instance-state-name",
         "Values": ["pending", "running", "stopping", "stopped"]},
    ])["Reservations"]
    instances = [item for reservation in reservations
                 for item in reservation["Instances"]]
    if len(instances) > 1:
        raise PermanentError("Hay más de una instancia para el mismo grupo")
    if instances:
        _apply_missing(ec2, instances[0]["InstanceId"],
                       _current_tags(instances[0]), tags)
        return instances[0]["InstanceId"]
    token = f"fenix-{group}-node"  # Estable entre reintentos del mismo grupo.
    return create_instance(image_id, security_group_id, token, tags)


def _ensure_bucket(s3, name: str, group: str, tags: dict[str, str]) -> str:
    """Reutiliza el bucket del grupo preservando etiquetas ajenas.

    Args:
        s3: Cliente S3 del emulador.
        name: Nombre estable del bucket del grupo.
        group: Identificador del grupo dueño del recurso.
        tags: Etiquetas obligatorias que debe tener el bucket.
    Returns:
        Nombre del bucket verificado.
    Raises:
        PermanentError: Si el bucket es de otro dueño o las etiquetas no quedan.
        ClientError: Si S3 rechaza la consulta o la escritura.
    """
    exists = any(bucket["Name"] == name
                 for bucket in s3.list_buckets()["Buckets"])
    if exists:
        try:
            current = {tag["Key"]: tag["Value"]
                       for tag in s3.get_bucket_tagging(Bucket=name)["TagSet"]}
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "NoSuchTagSet":
                raise  # Un error distinto de "sin etiquetas" no se oculta.
            current = {}
        if (current.get("ManagedBy") not in (None, "ppa2")
                or current.get("Project") not in (None, "fenix")
                or current.get("GroupId") not in (None, group)):
            raise PermanentError("Bucket ajeno con el mismo nombre")
        s3.put_bucket_tagging(Bucket=name,
            Tagging={"TagSet": aws_tags({**current, **tags})})
    else:
        create_bucket(name, tags)
    stored = {tag["Key"]: tag["Value"]
              for tag in s3.get_bucket_tagging(Bucket=name)["TagSet"]}
    if any(stored.get(key) != value for key, value in tags.items()):
        raise PermanentError("No se pudieron verificar las etiquetas del bucket")
    return name


def setup_demo(group: str) -> dict:
    """Prepara una instancia mock y un bucket a partir de identificadores estables.

    Args:
        group: ID validado del grupo; determina prefijos de los recursos.
    Returns:
        Inventario con aliases node-01 y bucket-01 y sus IDs reales del emulador.
        ``node-01`` incluye ``security_group_id`` y ambos aliases guardan
        ``expected_tags``; la clave reservada ``_lab`` conserva grupo, VPC, AMI
        y SG como punto de control. Los aliases cumplen ``[a-z0-9-]{3,32}`` y
        nunca colisionan con ``_lab``.
    Raises:
        ValidationError: Si group no cumple el contrato de identifier.
        PermanentError: Si el inventario o un recurso pertenecen a otro grupo.
        ClientError: Si el emulador no soporta una operación o falla su ejecución.
    Side Effects:
        Crea recursos de laboratorio etiquetados y data/inventory.json.
    Notes:
        Reutilizar por etiquetas antes de crear y guardar el inventario después
        de cada etapa. No se cambia el estado de una instancia ya existente:
        detenerla o repararla es tarea de I6 y del worker, no de setup-demo.
    """
    group = identifier(group)  # Rechaza grupos fuera del contrato de I1.
    inventory = load(INVENTORY_PATH)
    lab = inventory.get("_lab", {})
    if lab.get("group") not in (None, group):
        raise PermanentError("data/inventory.json pertenece a otro grupo")

    vpc_id, image_id = mock_inputs()  # Descubre VPC e ImageId del emulador.
    expected_tags = _required_tags(group)  # Solo las cuatro etiquetas exigidas.
    instance_name = f"fenix-{group}-node"
    instance_tags = {**expected_tags, "Name": instance_name}
    bucket_name = f"fenix-{group}-demo"
    sg_name = f"fenix-{group}-sg"

    ec2 = client("ec2")
    security_group_id = _ensure_security_group(ec2, group, sg_name, vpc_id,
                                               expected_tags)
    inventory["_lab"] = {
        "group": group,
        "region": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        "vpc_id": vpc_id,
        "image_id": image_id,
        "security_group_id": security_group_id,
        "security_group_name": sg_name,
        "instance_name": instance_name,
        "bucket_name": bucket_name,
    }
    save(INVENTORY_PATH, inventory)  # El SG ya está verificado.

    instance_id = _ensure_instance(ec2, group, instance_name, image_id,
                                   security_group_id, instance_tags)
    inventory["node-01"] = {"type": "ec2", "id": instance_id,
                            "security_group_id": security_group_id,
                            "expected_tags": expected_tags}
    save(INVENTORY_PATH, inventory)  # Guarda el ID real antes de seguir.

    bucket_id = _ensure_bucket(client("s3"), bucket_name, group, expected_tags)
    inventory["bucket-01"] = {"type": "s3", "id": bucket_id,
                              "expected_tags": expected_tags}
    save(INVENTORY_PATH, inventory)  # Inventario completo y verificado.
    return inventory


STOP_ATTEMPTS = 15  # Consultas acotadas después de stop_instances.
STOP_DELAY = 0.5  # Segundos entre consultas; no espera indefinida.


def _fault_instance(resource: dict) -> None:
    """Detiene la instancia del alias y verifica el estado final.

    Args:
        resource: Registro node-01 del inventario con su InstanceId real.
    Returns:
        None solo cuando EC2 informa el estado stopped.
    Raises:
        ValidationError: Si el registro no contiene un InstanceId válido.
        PermanentError: Si la instancia no existe o queda en un estado terminal.
        RetryableError: Si no llega a stopped dentro del plazo acotado.
        ClientError: Si EC2 rechaza la detención o una consulta.
    Side Effects:
        Detiene únicamente la instancia indicada por el inventario.
    """
    instance_id = resource.get("id")
    if not isinstance(instance_id, str) or not instance_id.startswith("i-"):
        raise ValidationError("El inventario no tiene un InstanceId válido")

    ec2 = client("ec2")
    ec2.stop_instances(InstanceIds=[instance_id])  # El alias ya resolvió el ID.
    for _ in range(STOP_ATTEMPTS):  # Consultas limitadas, sin bucle infinito.
        reservations = ec2.describe_instances(
            InstanceIds=[instance_id])["Reservations"]
        instances = [item for reservation in reservations
                     for item in reservation["Instances"]]
        if not instances:
            raise PermanentError("La instancia del inventario no existe")
        state = instances[0]["State"]["Name"]
        if state == "stopped":
            return  # El fallo quedó verificado mediante el SDK.
        if state in ("stopping", "pending", "running"):
            time.sleep(STOP_DELAY)  # La transición todavía no terminó.
            continue
        raise PermanentError(f"La instancia quedó en estado {state}")
    raise RetryableError("La instancia no llegó a stopped dentro del plazo")


def _fault_bucket(resource: dict, group: str | None) -> None:
    """Quita Owner del bucket propio conservando el resto de las etiquetas.

    Args:
        resource: Registro bucket-01 del inventario con su nombre real.
        group: Identificador del grupo dueño, leído de la clave _lab.
    Returns:
        None cuando Owner ya no está presente; repetir no cambia nada.
    Raises:
        ValidationError: Si el registro no contiene un nombre de bucket válido.
        PermanentError: Si el bucket no pertenece al grupo o no tiene etiquetas.
        RetryableError: Si Owner reaparece después de la escritura.
        ClientError: Si S3 rechaza una lectura o escritura de etiquetas.
    Side Effects:
        Reemplaza las etiquetas del bucket sin tocar otras claves.
    """
    bucket = resource.get("id")
    if not isinstance(bucket, str) or not bucket:
        raise ValidationError("El inventario no tiene un bucket válido")

    s3 = client("s3")
    try:
        current = {tag["Key"]: tag["Value"]
                   for tag in s3.get_bucket_tagging(Bucket=bucket)["TagSet"]}
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "NoSuchTagSet":
            raise  # Un error distinto de "sin etiquetas" no se oculta.
        current = {}
    if (current.get("ManagedBy") != "ppa2" or current.get("Project") != "fenix"
            or current.get("GroupId") != group):
        raise PermanentError("El bucket no pertenece al grupo del inventario")
    if "Owner" not in current:
        return  # Ya está en el estado de falla; no se reescriben etiquetas.

    remaining = [{"Key": key, "Value": value}
                 for key, value in current.items() if key != "Owner"]
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": remaining})
    stored = {tag["Key"] for tag in
              s3.get_bucket_tagging(Bucket=bucket)["TagSet"]}
    if "Owner" in stored:
        raise RetryableError("La etiqueta Owner sigue presente")


def inject_fault(alias: str) -> None:
    """Detiene el nodo o elimina una etiqueta del bucket de laboratorio.

    Args:
        alias: node-01 o bucket-01 presente en inventory.json.
    Returns:
        None cuando el fallo simulado se verifica mediante el SDK.
    Raises:
        ValidationError: Si el alias no pertenece al inventario.
        PermanentError: Si el recurso no pertenece al grupo o no existe.
        RetryableError: Si el estado de falla todavía no se observa.
        ClientError: Si EC2 o S3 rechazan una operación.
    Side Effects:
        Modifica únicamente el recurso de prueba de ese grupo.
    Notes:
        Esta función fabrica el problema; no debe enviar el evento automáticamente.
    """
    inventory = load(INVENTORY_PATH)  # El alias se resuelve siempre aquí.
    resource = inventory.get(alias)
    if not isinstance(resource, dict):
        raise ValidationError("El alias no pertenece al inventario")

    kind = resource.get("type")
    if alias == "node-01" and kind == "ec2":
        _fault_instance(resource)
        return
    if alias == "bucket-01" and kind == "s3":
        _fault_bucket(resource, inventory.get("_lab", {}).get("group"))
        return
    raise ValidationError("El alias no corresponde a un recurso conocido")
