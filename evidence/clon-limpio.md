# Verificación desde un clon limpio

- **Fecha:** 2026-11-17
- **Responsable:** I2 — Maldonado, Fernando Manuel (coordinador)
- **Rama / commit:** `main` / `500fed8`
- **Entorno:** Python 3.14.4 · Docker 29.1.3 · Docker Compose 2.40.3 · LocalStack 3.8.0 · Linux x86_64

## Preparación

Se clonó el repositorio desde GitHub en un directorio temporal vacío. No se
copiaron `.venv`, `.env`, `data/` ni `logs/` del entorno de desarrollo.

```bash
git clone git@github.com:Ferco7/fenix-autorepair.git fenix-clon
cd fenix-clon

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

cp .env.example .env
# Se generó un WEBHOOK_SECRET nuevo con secrets.token_urlsafe(32).
# El valor no se imprime ni se guarda en esta evidencia.
```

## Comando

```bash
git rev-parse HEAD
docker compose up -d --wait
.venv/bin/python scripts/doctor.py
.venv/bin/python -m pytest -q
docker compose down -v
```

## Resultado obtenido

```text
$ git rev-parse HEAD
500fed82c90b5f2f5164d3b28cd96f1c48f276f1

$ python3 --version
Python 3.14.4

Container fenix-localstack  Healthy

[OK] Python 3.14.4 (versión del grupo)
[OK] .env presente
[OK] Variables obligatorias definidas
[OK] WEBHOOK_SECRET con longitud suficiente
[OK] AWS_ENDPOINT_URL apunta al loopback :4566
[OK] Imagen fijada: localstack/localstack:3.8.0
[OK] GROUP_ID con formato válido
[OK] QUEUE_PREFIX con formato válido
[OK] Docker version 29.1.3, build 29.1.3-0ubuntu4.1
[OK] Docker Compose version 2.40.3+ds1-0ubuntu1
[OK] LocalStack disponible: sqs=available, s3=available, ec2=available

Resumen: 11 OK, 0 avisos, 0 fallos
Entorno listo para trabajar.

........................................................................ [ 66%]
....................................                                     [100%]
108 passed in 30.32s
```

Al finalizar se ejecutó `docker compose down -v`: el contenedor y la red se
eliminaron sin dejar recursos del ensayo.

## Observaciones

El commit verificado es `500fed8`, anterior a este archivo. Incorporar la
evidencia solo agrega documentación: no cambia código, dependencias ni pruebas.

## Qué verifica

- Que un clon nuevo instala el paquete y sus dependencias sin depender del
  entorno local.
- Que `.env.example` alcanza para configurar el proyecto completando solo
  `WEBHOOK_SECRET`.
- Que `doctor.py` valida Python, variables, Docker, Compose y LocalStack.
- Que la suite completa, incluidas las 4 pruebas de integración, pasa desde
  cero: **108 passed**.
- Que el procedimiento del README es reproducible por otra persona.
