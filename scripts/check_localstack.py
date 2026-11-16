#!/usr/bin/env python3
"""Smoke real de LocalStack con Boto3, independiente del código de los roles.

Crea recursos efímeros con un prefijo único, verifica SQS + DLQ, S3 con tags
y EC2 mock (stop/start), y limpia todo al finalizar.

Uso:
    .venv/bin/python scripts/check_localstack.py

Requiere LocalStack en http://localhost:4566 y el paquete instalado
(`pip install -e .`), porque reutiliza el guardián de fenix.config.settings.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from fenix.config.settings import client
from fenix.utils.errors import ProjectError

ROOT = Path(__file__).resolve().parent.parent
TAGS = [
    {"Key": "ManagedBy", "Value": "ppa2"},
    {"Key": "Project", "Value": "fenix"},
    {"Key": "GroupId", "Value": "smoke"},
    {"Key": "Owner", "Value": "smoke"},
]


def ok(message: str) -> None:
    """Informa un paso correcto."""
    print(f"[OK]   {message}")


def fail(message: str, error: Exception | None = None) -> None:
    """Informa un paso fallido sin ocultar el tipo de error."""
    detail = f" -> {type(error).__name__}: {error}" if error else ""
    print(f"[FAIL] {message}{detail}")


def wait_state(ec2, instance_id: str, expected: str, tries: int = 15) -> bool:
    """Espera acotada de un estado EC2 mock."""
    for _ in range(tries):
        reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
        state = reservations[0]["Instances"][0]["State"]["Name"]
        if state == expected:
            return True
        time.sleep(1)
    return False


def _error_code(error: Exception) -> str:
    """Devuelve el código de Boto3 sin exponer credenciales ni URLs."""
    if isinstance(error, ClientError):
        return error.response.get("Error", {}).get("Code", "ClientError")
    return type(error).__name__


def _terminate_instance(ec2, instance_id: str) -> bool:
    """Termina la instancia efímera; informa si no pudo hacerlo."""
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
        wait_state(ec2, instance_id, "terminated", tries=10)
        return True
    except (BotoCoreError, ClientError) as error:
        print(f"[WARN] No se pudo terminar la instancia {instance_id}: {_error_code(error)}")
        return False


def _delete_security_group(ec2, group_id: str) -> bool:
    """Borra el SG con reintentos acotados mientras EC2 libera la ENI."""
    last_code = "ClientError"
    for _ in range(10):
        try:
            ec2.delete_security_group(GroupId=group_id)
            return True
        except ClientError as error:
            last_code = _error_code(error)
            time.sleep(1)
    print(f"[WARN] No se pudo eliminar el SG {group_id}: {last_code}")
    return False


def _delete_bucket(s3, bucket: str) -> bool:
    """Borra el bucket efímero sin ocultar el error de Boto3."""
    try:
        s3.delete_bucket(Bucket=bucket)
        return True
    except ClientError as error:
        print(f"[WARN] No se pudo eliminar el bucket {bucket}: {_error_code(error)}")
        return False


def _delete_queue(sqs, url: str) -> bool:
    """Borra una cola efímera sin ocultar el error de Boto3."""
    try:
        sqs.delete_queue(QueueUrl=url)
        return True
    except ClientError as error:
        print(f"[WARN] No se pudo eliminar la cola {url}: {_error_code(error)}")
        return False


def _cleanup(instance_id, group_id, bucket, work_url, dlq_url) -> int:
    """Limpia los recursos del smoke y devuelve cuántos no pudo borrar."""
    problems = 0
    if instance_id and not _terminate_instance(client("ec2"), instance_id):
        problems += 1
    if group_id and not _delete_security_group(client("ec2"), group_id):
        problems += 1
    if bucket and not _delete_bucket(client("s3"), bucket):
        problems += 1
    if work_url and not _delete_queue(client("sqs"), work_url):
        problems += 1
    if dlq_url and not _delete_queue(client("sqs"), dlq_url):
        problems += 1
    if problems:
        print(f"[WARN] Limpieza incompleta: {problems} recurso(s) sin eliminar")
    else:
        ok("Limpieza de recursos efímeros")
    return problems


def main() -> int:
    """Ejecuta el smoke y limpia los recursos creados."""
    os.chdir(ROOT)
    suffix = f"{os.getpid()}"
    prefix = f"fenix-smoke-{suffix}"
    bucket = f"{prefix}-demo"
    instance_id: str | None = None
    group_id: str | None = None
    work_url: str | None = None
    dlq_url: str | None = None
    failures = 0

    try:
        sqs = client("sqs")
        s3 = client("s3")
        ec2 = client("ec2")

        # ---------- SQS + DLQ ----------
        dlq_url = sqs.create_queue(
            QueueName=f"{prefix}-dlq",
            Attributes={"MessageRetentionPeriod": "1209600"},
        )["QueueUrl"]
        dlq_arn = sqs.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        work_url = sqs.create_queue(
            QueueName=f"{prefix}-events",
            Attributes={
                "VisibilityTimeout": "45",
                "MessageRetentionPeriod": "345600",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}
                ),
            },
        )["QueueUrl"]
        sqs.set_queue_attributes(
            QueueUrl=work_url,
            Attributes={
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}
                )
            },
        )
        attributes = sqs.get_queue_attributes(
            QueueUrl=work_url, AttributeNames=["VisibilityTimeout", "RedrivePolicy"]
        )["Attributes"]
        assert attributes["VisibilityTimeout"] == "45"
        assert "maxReceiveCount" in attributes["RedrivePolicy"]
        ok("SQS: cola principal con VisibilityTimeout=45 y RedrivePolicy maxReceiveCount=3")

        sqs.send_message(QueueUrl=work_url, MessageBody='{"smoke": true}')
        messages = sqs.receive_message(
            QueueUrl=work_url, MaxNumberOfMessages=1, VisibilityTimeout=45
        ).get("Messages", [])
        assert messages, "receive_message no devolvió el mensaje enviado"
        sqs.delete_message(QueueUrl=work_url, ReceiptHandle=messages[0]["ReceiptHandle"])
        ok("SQS: send -> receive -> delete (ACK)")

        # ---------- S3 ----------
        s3.create_bucket(Bucket=bucket)
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": TAGS})
        stored = s3.get_bucket_tagging(Bucket=bucket)["TagSet"]
        assert {tag["Key"] for tag in stored} >= {"ManagedBy", "Project", "GroupId", "Owner"}
        ok("S3: bucket creado con las cuatro etiquetas obligatorias")

        # ---------- EC2 mock ----------
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"]
        assert vpcs, "no hay VPC predeterminada en el emulador"
        vpc_id = vpcs[0]["VpcId"]
        images = ec2.describe_images()["Images"]
        assert images, "describe_images no devolvió AMIs emuladas"
        image_id = sorted(images, key=lambda item: item["ImageId"])[0]["ImageId"]
        ok(f"EC2: VPC {vpc_id} y AMI mock {image_id}")

        group_id = ec2.create_security_group(
            GroupName=f"{prefix}-sg",
            Description="Smoke test efímero de Fénix",
            VpcId=vpc_id,
            TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}],
        )["GroupId"]
        instance = ec2.run_instances(
            ImageId=image_id,
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
            SecurityGroupIds=[group_id],
            ClientToken=prefix,
            TagSpecifications=[{"ResourceType": "instance", "Tags": TAGS}],
        )["Instances"][0]
        instance_id = instance["InstanceId"]
        ok(f"EC2: instancia {instance_id} creada con ClientToken idempotente")

        ec2.stop_instances(InstanceIds=[instance_id])
        assert wait_state(ec2, instance_id, "stopped"), "la instancia no llegó a stopped"
        ec2.start_instances(InstanceIds=[instance_id])
        assert wait_state(ec2, instance_id, "running"), "la instancia no llegó a running"
        tags = ec2.describe_tags(
            Filters=[{"Name": "resource-id", "Values": [instance_id]}]
        )["Tags"]
        assert {tag["Key"] for tag in tags} >= {"ManagedBy", "Project", "GroupId", "Owner"}
        ok("EC2: stop -> stopped -> start -> running y tags verificados")

    except (ProjectError, BotoCoreError, ClientError, AssertionError, OSError, ValueError) as error:
        failures += 1
        fail("Smoke de LocalStack", error)
    finally:
        # Sin return, break ni continue: la limpieza informa y suma fallos.
        failures += _cleanup(instance_id, group_id, bucket, work_url, dlq_url)

    print("\nResultado:", "smoke OK" if failures == 0 else f"{failures} fallo(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
