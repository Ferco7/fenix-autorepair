"""Pruebas del rol I2: colas idempotentes, DLQ y backoff sin reenvío."""
import json  # Verifica la política de redrive serializada.
import uuid  # Genera un prefijo exclusivo para la prueba de integración.
import warnings  # Hace visible una limpieza incompleta, sin ocultarla.
import pytest  # Parametriza el backoff y marca la prueba de integración.
from botocore.exceptions import ClientError
from fenix.services import sqs as sqs_module


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
