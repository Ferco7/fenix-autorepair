"""Pruebas de inyección de fallas del laboratorio (I6)."""
import json

import pytest
from botocore.exceptions import ClientError

from fenix.services import demo as demo_module
from fenix.utils.errors import PermanentError, RetryableError, ValidationError


class FakeEC2:
    """Cliente EC2 mínimo: registra la detención y devuelve estados preparados."""

    def __init__(self, states):
        self.states = list(states)
        self.stops = []
        self.queries = 0

    def stop_instances(self, InstanceIds):
        self.stops.append(list(InstanceIds))
        return {"StoppingInstances": [{"InstanceId": InstanceIds[0]}]}

    def describe_instances(self, InstanceIds):
        self.queries += 1
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"Reservations": [{"Instances": [
            {"InstanceId": InstanceIds[0], "State": {"Name": state}}]}]}


class FakeS3:
    """Cliente S3 mínimo que conserva las etiquetas entre lecturas y escrituras."""

    def __init__(self, tags=None, missing=False):
        self.tags = dict(tags or {})
        self.missing = missing
        self.puts = []

    def get_bucket_tagging(self, Bucket):
        if self.missing:
            raise ClientError({"Error": {"Code": "NoSuchTagSet", "Message": "x"}},
                              "GetBucketTagging")
        return {"TagSet": [{"Key": key, "Value": value}
                           for key, value in self.tags.items()]}

    def put_bucket_tagging(self, Bucket, Tagging):
        self.puts.append({tag["Key"]: tag["Value"] for tag in Tagging["TagSet"]})
        self.tags = dict(self.puts[-1])
        return {}


def preparar(tmp_path, monkeypatch, ec2=None, s3=None):
    """Escribe un inventario propio y dirige demo.client a los fakes."""
    ruta = tmp_path / "inventory.json"
    ruta.write_text(json.dumps({
        "_lab": {"group": "grupo01"},
        "node-01": {"type": "ec2", "id": "i-1", "security_group_id": "sg-1",
                    "expected_tags": {}},
        "bucket-01": {"type": "s3", "id": "b-1", "expected_tags": {}},
    }), encoding="utf-8")
    monkeypatch.setattr(demo_module, "INVENTORY_PATH", str(ruta))
    monkeypatch.setattr(demo_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(demo_module, "client",
                        lambda service: ec2 if service == "ec2" else s3)
    return ruta


def test_alias_desconocido_no_toca_cloud(tmp_path, monkeypatch):
    """Un alias fuera del inventario se rechaza antes de llamar a AWS."""
    ec2, s3 = FakeEC2(["stopped"]), FakeS3()
    preparar(tmp_path, monkeypatch, ec2, s3)

    with pytest.raises(ValidationError):
        demo_module.inject_fault("i-12345")
    assert ec2.stops == [] and s3.puts == []


def test_alias_con_tipo_incorrecto_no_toca_cloud(tmp_path, monkeypatch):
    """El alias debe apuntar al tipo de recurso previsto."""
    ruta = preparar(tmp_path, monkeypatch, FakeEC2(["stopped"]), FakeS3())
    inventario = json.loads(ruta.read_text(encoding="utf-8"))
    inventario["node-01"]["type"] = "s3"
    ruta.write_text(json.dumps(inventario), encoding="utf-8")

    with pytest.raises(ValidationError):
        demo_module.inject_fault("node-01")


def test_node01_detiene_y_verifica_stopped(tmp_path, monkeypatch):
    """F10/F02: se detiene el ID del inventario y se espera el estado final."""
    ec2 = FakeEC2(["stopping", "stopped"])
    preparar(tmp_path, monkeypatch, ec2, FakeS3())

    demo_module.inject_fault("node-01")

    assert ec2.stops == [["i-1"]]
    assert ec2.queries == 2


def test_node01_estado_terminal_es_permanente(tmp_path, monkeypatch):
    """Una instancia terminada no se puede detener: falla explicada."""
    ec2 = FakeEC2(["terminated"])
    preparar(tmp_path, monkeypatch, ec2, FakeS3())

    with pytest.raises(PermanentError):
        demo_module.inject_fault("node-01")


def test_node01_agota_consultas_acotadas(tmp_path, monkeypatch):
    """Si nunca llega a stopped, no se consulta para siempre."""
    ec2 = FakeEC2(["running"])
    preparar(tmp_path, monkeypatch, ec2, FakeS3())

    with pytest.raises(RetryableError):
        demo_module.inject_fault("node-01")
    assert ec2.queries == demo_module.STOP_ATTEMPTS


def test_bucket01_quita_owner_y_preserva_el_resto(tmp_path, monkeypatch):
    """Solo se elimina Owner; las demás etiquetas quedan intactas."""
    s3 = FakeS3({"ManagedBy": "ppa2", "Project": "fenix",
                 "GroupId": "grupo01", "Owner": "grupo01",
                 "Ambiente": "laboratorio"})
    preparar(tmp_path, monkeypatch, FakeEC2(["stopped"]), s3)

    demo_module.inject_fault("bucket-01")

    assert s3.puts == [{"ManagedBy": "ppa2", "Project": "fenix",
                        "GroupId": "grupo01", "Ambiente": "laboratorio"}]
    assert "Owner" not in s3.tags


def test_bucket01_sin_owner_es_idempotente(tmp_path, monkeypatch):
    """Repetir la falla ya aplicada no reescribe el bucket."""
    s3 = FakeS3({"ManagedBy": "ppa2", "Project": "fenix", "GroupId": "grupo01"})
    preparar(tmp_path, monkeypatch, FakeEC2(["stopped"]), s3)

    demo_module.inject_fault("bucket-01")
    assert s3.puts == []


def test_bucket01_ajeno_no_se_modifica(tmp_path, monkeypatch):
    """Un bucket con GroupId distinto no se toca aunque el alias exista."""
    s3 = FakeS3({"ManagedBy": "ppa2", "Project": "fenix",
                 "GroupId": "otro-grupo", "Owner": "otro-grupo"})
    preparar(tmp_path, monkeypatch, FakeEC2(["stopped"]), s3)

    with pytest.raises(PermanentError):
        demo_module.inject_fault("bucket-01")
    assert s3.puts == []


def test_bucket01_sin_tags_no_se_modifica(tmp_path, monkeypatch):
    """Sin etiquetas no se puede demostrar pertenencia; no se escribe."""
    s3 = FakeS3(missing=True)
    preparar(tmp_path, monkeypatch, FakeEC2(["stopped"]), s3)

    with pytest.raises(PermanentError):
        demo_module.inject_fault("bucket-01")
    assert s3.puts == []
