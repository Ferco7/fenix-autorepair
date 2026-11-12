#!/usr/bin/env python3
"""Diagnóstico local del entorno Fénix.

Verifica versión de Python, archivo .env, variables obligatorias, destino
loopback, imagen de LocalStack, Docker/Compose y salud del emulador.
No imprime secretos: solo indica si están definidos.

Uso:
    .venv/bin/python scripts/doctor.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

REQUIRED_VARS = (
    "AWS_ENDPOINT_URL",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "GROUP_ID",
    "QUEUE_PREFIX",
    "WEBHOOK_SECRET",
    "LOCALSTACK_IMAGE",
)

RESULTS: list[tuple[str, str]] = []


def report(status: str, message: str) -> None:
    """Guarda y muestra una comprobación con su estado."""
    RESULTS.append((status, message))
    print(f"[{status}] {message}")


def read_env(path: Path) -> dict[str, str]:
    """Lee .env sin dependencias externas.

    Respeta el mismo criterio que python-dotenv: las variables ya exportadas
    en el proceso tienen prioridad sobre el archivo.
    """
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_python() -> None:
    """Comprueba el mínimo de la consigna y la versión usada por el grupo."""
    if sys.version_info < (3, 11):
        report("FAIL", f"Python {sys.version.split()[0]}: se requiere 3.11 o superior")
    elif sys.version_info[:2] == (3, 14):
        report("OK", f"Python {sys.version.split()[0]} (versión del grupo)")
    else:
        report("WARN", f"Python {sys.version.split()[0]}: el grupo usa 3.14; unificar antes de entregar")


def check_env_file() -> None:
    """Verifica que exista el archivo local ignorado por Git."""
    if ENV_FILE.exists():
        report("OK", ".env presente")
    else:
        report("FAIL", "Falta .env: ejecutar `cp .env.example .env` y completar WEBHOOK_SECRET")


def check_required(env: dict[str, str]) -> None:
    """Comprueba variables obligatorias sin mostrar sus valores."""
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    if missing:
        report("FAIL", "Variables vacías o ausentes: " + ", ".join(missing))
    else:
        report("OK", "Variables obligatorias definidas")

    secret = env.get("WEBHOOK_SECRET", "")
    if secret and len(secret) < 16:
        report("FAIL", "WEBHOOK_SECRET debe tener al menos 16 caracteres")
    elif secret:
        report("OK", "WEBHOOK_SECRET con longitud suficiente")


def check_endpoint(env: dict[str, str]) -> None:
    """Exige el mismo destino loopback que valida fenix.config.settings."""
    raw = env.get("AWS_ENDPOINT_URL", "")
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        report("FAIL", "AWS_ENDPOINT_URL malformada")
        return
    valid = (
        parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
        and port == 4566
        and not parsed.username
        and not parsed.password
    )
    if valid:
        report("OK", "AWS_ENDPOINT_URL apunta al loopback :4566")
    else:
        report("FAIL", "AWS_ENDPOINT_URL debe ser http://localhost:4566 (sin credenciales en la URL)")


def check_image(env: dict[str, str]) -> None:
    """Detecta imágenes que exigen token o que no están fijadas."""
    image = env.get("LOCALSTACK_IMAGE", "")
    token = env.get("LOCALSTACK_AUTH_TOKEN", "")
    if not image:
        report("FAIL", "LOCALSTACK_IMAGE vacía")
    elif image.endswith(":latest"):
        report("FAIL", "No usar :latest: la imagen actual exige token y cambia sin aviso")
    elif "2026" in image and not token:
        report("FAIL", f"{image} exige LOCALSTACK_AUTH_TOKEN (Exited 55)")
    else:
        report("OK", f"Imagen fijada: {image}")


def check_ids(env: dict[str, str]) -> None:
    """Valida los identificadores usados en nombres de recursos."""
    pattern = re.compile(r"[a-z0-9-]{3,32}")
    for name in ("GROUP_ID", "QUEUE_PREFIX"):
        value = env.get(name, "")
        if value and pattern.fullmatch(value):
            report("OK", f"{name} con formato válido")
        elif value:
            report("FAIL", f"{name} debe cumplir [a-z0-9-]{{3,32}}")


def check_docker() -> None:
    """Comprueba Docker y el plugin Compose."""
    if not shutil.which("docker"):
        report("FAIL", "docker no está en PATH")
        return
    try:
        version = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        report("OK", version)
    except (subprocess.SubprocessError, OSError):
        report("FAIL", "No se pudo ejecutar docker --version")
        return
    try:
        compose = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        report("OK", compose)
    except (subprocess.SubprocessError, OSError):
        report("FAIL", "Falta el plugin `docker compose`")


def check_localstack() -> None:
    """Comprueba el puerto y la salud de los servicios requeridos."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        if sock.connect_ex(("127.0.0.1", 4566)) != 0:
            report("WARN", "LocalStack no responde en 127.0.0.1:4566 (¿docker compose up -d?)")
            return
    try:
        with urlopen("http://127.0.0.1:4566/_localstack/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        report("FAIL", "El puerto 4566 responde, pero /_localstack/health no es JSON válido")
        return
    services = health.get("services", {})
    required = ("sqs", "s3", "ec2")
    states = {name: services.get(name, "disabled") for name in required}
    if all(state == "available" for state in states.values()):
        report("OK", "LocalStack disponible: " + ", ".join(required))
    else:
        report("FAIL", "Servicios no disponibles: " + json.dumps(states))


def main() -> int:
    """Ejecuta todas las comprobaciones y devuelve un código de salida."""
    os.chdir(ROOT)
    print(f"Fénix · diagnóstico local\nRaíz: {ROOT}\nIntérprete: {sys.executable}\n")
    env = {**read_env(ENV_FILE), **os.environ}

    check_python()
    check_env_file()
    check_required(env)
    check_endpoint(env)
    check_image(env)
    check_ids(env)
    check_docker()
    check_localstack()

    failures = sum(1 for status, _ in RESULTS if status == "FAIL")
    warnings = sum(1 for status, _ in RESULTS if status == "WARN")
    print(f"\nResumen: {len(RESULTS) - failures - warnings} OK, {warnings} avisos, {failures} fallos")
    if failures:
        print("Corregir los FAIL antes de ejecutar el flujo del TP.")
        return 1
    print("Entorno listo para trabajar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
