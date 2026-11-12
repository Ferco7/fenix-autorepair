"""Pruebas del rol I2: colas idempotentes, DLQ y backoff sin reenvío."""
import json  # Verifica la política de redrive serializada.
import time  # Espera acotada durante la limpieza de recursos.
import uuid  # Genera un prefijo exclusivo para la prueba de integración.
import warnings  # Hace visible una limpieza incompleta, sin ocultarla.
import pytest  # Parametriza el backoff y marca la prueba de integración.
from botocore.exceptions import ClientError
from fenix.services import demo as demo_module
from fenix.services import sqs as sqs_module
from fenix.utils.errors import PermanentError


class FakeSQS:
    """Cliente SQS mínimo: registra llamadas y conserva las URLs creadas."""

    def __init__(self):
        """Inicializa el registro de llamadas y las colas simuladas."""
        self.calls = []
        self.queues = {}

    def create_queue(self, QueueName, Attributes=None):
        """Devuelve la misma URL si la cola ya existe, como SQS real."""
        attributes = dict(Attributes or {})
        self.calls.append(("create_queue", QueueName, attributes))
        if QueueName not in self.queues:
            self.queues[QueueName] = {
                "url": f"http://localhost:4566/000000000000/{QueueName}",
                "attributes": attributes,
            }
        return {"QueueUrl": self.queues[QueueName]["url"]}

    def get_queue_attributes(self, QueueUrl, AttributeNames):
        """Entrega el ARN derivado del nombre, sin inventar identificadores."""
        self.calls.append(("get_queue_attributes", QueueUrl, tuple(AttributeNames)))
        name = QueueUrl.rsplit("/", 1)[-1]
        return {"Attributes": {"QueueArn": f"arn:aws:sqs:us-east-1:000000000000:{name}"}}

    def set_queue_attributes(self, QueueUrl, Attributes):
        """Registra la política forzada sobre una cola que ya existía."""
        self.calls.append(("set_queue_attributes", QueueUrl, dict(Attributes)))
        name = QueueUrl.rsplit("/", 1)[-1]
        self.queues[name]["attributes"].update(Attributes)

    def change_message_visibility(self, QueueUrl, ReceiptHandle, VisibilityTimeout):
        """Registra el cambio de visibilidad del mensaje original."""
        self.calls.append(
            ("change_message_visibility", QueueUrl, ReceiptHandle, VisibilityTimeout)
        )

    def send_message(self, **kwargs):
        """Falla si el reintento intenta crear una copia del mensaje."""
        raise AssertionError("retry_later no debe reenviar con send_message")


@pytest.fixture
def fake_sqs(monkeypatch):
    """Reemplaza el cliente real por el falso durante cada prueba unitaria."""
    fake = FakeSQS()
    monkeypatch.setattr(sqs_module, "client", lambda service: fake)
    return fake


@pytest.mark.pendiente
def test_ensure_queues_creates_dlq_first_and_forces_redrive(fake_sqs):
    """Crea la DLQ antes que la cola principal y fuerza la RedrivePolicy.

    Returns:
        None si el orden y los atributos cumplen el contrato.
    Raises:
        AssertionError: Si falta un atributo o se invierte el orden.
    """
    work, dead = sqs_module.ensure_queues("fenix-i2")

    assert work.endswith("/fenix-i2-events")
    assert dead.endswith("/fenix-i2-dlq")
    assert [call[0] for call in fake_sqs.calls] == [
        "create_queue",
        "get_queue_attributes",
        "create_queue",
        "set_queue_attributes",
    ]
    assert fake_sqs.calls[0][1] == "fenix-i2-dlq"
    assert fake_sqs.calls[2][1] == "fenix-i2-events"

    attributes = fake_sqs.calls[2][2]
    assert attributes["VisibilityTimeout"] == "45"
    assert attributes["MessageRetentionPeriod"] == "345600"
    policy = json.loads(attributes["RedrivePolicy"])
    assert policy == {
        "deadLetterTargetArn": "arn:aws:sqs:us-east-1:000000000000:fenix-i2-dlq",
        "maxReceiveCount": 3,
    }
    assert fake_sqs.calls[3][2]["RedrivePolicy"] == attributes["RedrivePolicy"]


@pytest.mark.pendiente
def test_ensure_queues_is_idempotent(fake_sqs):
    """Repetir la preparación conserva las mismas URLs y no duplica colas.

    Returns:
        None si dos llamadas devuelven los mismos identificadores.
    Raises:
        AssertionError: Si la segunda llamada crea recursos distintos.
    """
    first = sqs_module.ensure_queues("fenix-i2")
    second = sqs_module.ensure_queues("fenix-i2")

    assert first == second
    assert sorted(fake_sqs.queues) == ["fenix-i2-dlq", "fenix-i2-events"]


@pytest.mark.pendiente
@pytest.mark.parametrize(
    ("count", "expected"),
    [("1", 2), ("2", 4), ("3", 8), ("10", 30)],
)
def test_retry_later_applies_bounded_backoff(fake_sqs, count, expected):
    """Calcula min(30, 2 ** recepción) y cambia la visibilidad del original.

    Args:
        count: ApproximateReceiveCount entregado por SQS.
        expected: Segundos esperados para esa recepción.

    Returns:
        None si el backoff coincide y no se reenvía el mensaje.
    Raises:
        AssertionError: Si el cálculo o el método usado son incorrectos.
    """
    message = {
        "ReceiptHandle": "rh-1",
        "Attributes": {"ApproximateReceiveCount": count},
    }

    seconds = sqs_module.retry_later("http://localhost:4566/q", message)

    assert seconds == expected
    assert fake_sqs.calls == [
        ("change_message_visibility", "http://localhost:4566/q", "rh-1", expected)
    ]


@pytest.mark.integracion
def test_ensure_queues_against_localstack():
    """Verifica colas, retenciones y DLQ contra el emulador real.

    Returns:
        None si los atributos leídos coinciden con la configuración pedida.
    Raises:
        ClientError: Si LocalStack no responde o rechaza una operación.
    Side Effects:
        Crea un par de colas con prefijo único y las elimina al finalizar.
    """
    prefix = f"fenix-i2-{uuid.uuid4().hex[:8]}"
    sqs = sqs_module.client("sqs")
    work_url = None
    dead_url = None
    try:
        work_url, dead_url = sqs_module.ensure_queues(prefix)
        assert (work_url, dead_url) == sqs_module.ensure_queues(prefix)

        work = sqs.get_queue_attributes(
            QueueUrl=work_url,
            AttributeNames=[
                "VisibilityTimeout",
                "MessageRetentionPeriod",
                "RedrivePolicy",
            ],
        )["Attributes"]
        dead = sqs.get_queue_attributes(
            QueueUrl=dead_url,
            AttributeNames=["MessageRetentionPeriod", "QueueArn"],
        )["Attributes"]

        assert work["VisibilityTimeout"] == "45"
        assert work["MessageRetentionPeriod"] == "345600"
        assert dead["MessageRetentionPeriod"] == "1209600"

        policy = json.loads(work["RedrivePolicy"])
        assert policy["deadLetterTargetArn"] == dead["QueueArn"]
        assert int(policy["maxReceiveCount"]) == 3
    finally:
        for url in (work_url, dead_url):
            if url is not None:
                try:
                    sqs.delete_queue(QueueUrl=url)
                except ClientError as error:
                    warnings.warn(
                        f"No se pudo limpiar la cola de prueba {url}: {error}",
                        stacklevel=1,
                    )


@pytest.mark.pendiente
def test_setup_demo_rejects_inventory_from_another_group(tmp_path, monkeypatch):
    """No reutiliza un inventario que pertenece a otro grupo.

    Args:
        tmp_path: Archivo temporal para el inventario.
        monkeypatch: Sustituye la ruta y la validación de I1.

    Returns:
        None si el conflicto se detecta antes de tocar el emulador.
    Raises:
        AssertionError: Si el inventario ajeno se acepta.
    """
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"_lab": {"group": "otro-grupo"}}), encoding="utf-8")
    monkeypatch.setattr(demo_module, "INVENTORY_PATH", str(path))
    monkeypatch.setattr(demo_module, "identifier", lambda value: value)

    with pytest.raises(PermanentError):
        demo_module.setup_demo("grupo-01")


def _cleanup_lab(ec2, s3, inventory: dict) -> None:
    """Elimina los recursos del ensayo sin ocultar una limpieza incompleta.

    Args:
        ec2: Cliente EC2 usado por el ensayo.
        s3: Cliente S3 usado por el ensayo.
        inventory: Inventario con los IDs reales a eliminar.

    Returns:
        None.
    Side Effects:
        Termina la instancia, borra el SG y el bucket; avisa si algo falla.
    """
    instance_id = inventory.get("node-01", {}).get("id")
    if instance_id:
        try:
            ec2.terminate_instances(InstanceIds=[instance_id])
            for _ in range(20):
                state = ec2.describe_instances(InstanceIds=[instance_id])[
                    "Reservations"][0]["Instances"][0]["State"]["Name"]
                if state == "terminated":
                    break
                time.sleep(1)
        except ClientError as error:
            warnings.warn(
                f"No se pudo terminar la instancia {instance_id}: {error}",
                stacklevel=1,
            )

    security_group_id = inventory.get("_lab", {}).get("security_group_id")
    if security_group_id:
        for _ in range(10):
            try:
                ec2.delete_security_group(GroupId=security_group_id)
                break
            except ClientError:
                time.sleep(1)
        else:
            warnings.warn(
                f"No se pudo eliminar el SG {security_group_id}",
                stacklevel=1,
            )

    bucket_id = inventory.get("bucket-01", {}).get("id")
    if bucket_id:
        try:
            s3.delete_bucket(Bucket=bucket_id)
        except ClientError as error:
            warnings.warn(
                f"No se pudo eliminar el bucket {bucket_id}: {error}",
                stacklevel=1,
            )


@pytest.mark.integracion
def test_setup_demo_is_idempotent_against_localstack(tmp_path, monkeypatch):
    """Repite setup-demo y conserva los IDs reales de instancia, SG y bucket.

    Args:
        tmp_path: Archivo temporal para no tocar el inventario del grupo.
        monkeypatch: Sustituye la ruta y la validación de I1.

    Returns:
        None si la segunda corrida reutiliza los mismos recursos y etiquetas.
    Raises:
        AssertionError: Si se duplican recursos o faltan etiquetas.
        ClientError: Si LocalStack rechaza una operación.
    Side Effects:
        Crea recursos con un grupo único y los elimina al finalizar.
    """
    group = f"i2-{uuid.uuid4().hex[:8]}"
    path = tmp_path / "inventory.json"
    monkeypatch.setattr(demo_module, "INVENTORY_PATH", str(path))
    monkeypatch.setattr(demo_module, "identifier", lambda value: value)

    ec2 = demo_module.client("ec2")
    s3 = demo_module.client("s3")
    inventory = {}
    try:
        first = demo_module.setup_demo(group)
        second = demo_module.setup_demo(group)
        inventory = second

        assert first["node-01"]["id"] == second["node-01"]["id"]
        assert first["bucket-01"]["id"] == second["bucket-01"]["id"]
        assert (first["_lab"]["security_group_id"]
                == second["_lab"]["security_group_id"])
        assert second["node-01"]["type"] == "ec2"
        assert second["bucket-01"]["type"] == "s3"
        assert second["node-01"]["tags"]["ManagedBy"] == "ppa2"
        assert second["bucket-01"]["tags"]["Owner"] == group
        assert second["_lab"]["vpc_id"].startswith("vpc-")
        assert second["_lab"]["image_id"].startswith("ami-")
        assert json.loads(path.read_text(encoding="utf-8")) == second

        node_tags = {
            tag["Key"]: tag["Value"]
            for tag in ec2.describe_tags(
                Filters=[{"Name": "resource-id",
                          "Values": [second["node-01"]["id"]]}]
            )["Tags"]
        }
        assert {"ManagedBy", "Project", "GroupId", "Owner"} <= node_tags.keys()

        bucket_tags = {
            tag["Key"]: tag["Value"]
            for tag in s3.get_bucket_tagging(
                Bucket=second["bucket-01"]["id"])["TagSet"]
        }
        assert bucket_tags["ManagedBy"] == "ppa2"
        assert bucket_tags["Owner"] == group
    finally:
        if path.exists():
            inventory = json.loads(path.read_text(encoding="utf-8"))
        _cleanup_lab(ec2, s3, inventory)
