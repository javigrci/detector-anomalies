# Security Log Anomaly Detector

Prototipo de apoyo al análisis de seguridad (SOC): ingerirá logs de auditoría, los puntuará con
Isolation Forest y expondrá los resultados por API REST.

> **Estado: incremento 0 (base del repositorio).** Solo existen el esqueleto del servicio, las
> sondas `/health` y `/ready`, la configuración, el logging estructurado, el entorno con Docker
> Compose y la CI. Todavía no hay ingesta, modelo ni autenticación.
>
> Una anomalía no implica un ataque, y el `anomaly_score` futuro no es una probabilidad de
> intrusión.

Documentación del proyecto: [constitución](.specify/memory/constitution.md) ·
[SPEC.md](SPEC.md) · [roadmap](docs/roadmap.md) · [decisiones](docs/decisions/) ·
[especificación del incremento 0](specs/000-base/spec.md)

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 y las dependencias).
- Docker con Compose. En Windows con WSL2, activa la integración de Docker Desktop con tu
  distribución (Settings → Resources → WSL integration).

## Instalación

```bash
uv sync --frozen
```

`--frozen` instala exactamente lo fijado en `uv.lock` y falla si `pyproject.toml` y el lock no
coinciden.

## Configuración

```bash
cp .env.example .env
```

Edita `.env` y cambia `POSTGRES_PASSWORD` (y la misma clave dentro de `DATABASE_URL` si ejecutas
fuera de Compose). La clave debe ser apta para URL: sin `@ : / ? # %`. `.env` está excluido de
Git; nunca lo subas. Las variables están descritas en
[specs/000-base/contracts/environment.md](specs/000-base/contracts/environment.md).

Si falta una variable obligatoria o es inválida, el servicio termina con un mensaje que nombra la
variable y nunca muestra su valor.

## Arrancar y detener

```bash
docker compose up --build -d --wait   # API + PostgreSQL 16
docker compose down                   # detener (añade -v para borrar también los datos)
```

La API queda en `http://127.0.0.1:${API_PORT:-8000}` (solo accesible desde tu máquina). La base de
datos no se publica en el host. Si el puerto está ocupado, cambia `API_PORT` en `.env`.

La API arranca aunque la base de datos no esté disponible: `/health` responde igualmente y
`/ready` indica no disponible hasta que la base de datos responda.

## Sondas

| Ruta | Respuesta | Significado |
|---|---|---|
| `GET /health` | `200 {"status":"ok"}` | El proceso está vivo; no consulta la base de datos. |
| `GET /ready` | `200 {"status":"ready","checks":{"database":"ok"}}` | Listo para recibir tráfico. |
| `GET /ready` | `503` con `code: "not_ready"` | La base de datos no responde. |

Son públicas y están fuera del prefijo `/api/v1`. Documentación interactiva en `/docs` y esquema
en `/openapi.json`.

Cada respuesta incluye la cabecera `X-Request-ID`. Si envías una válida (`[A-Za-z0-9._-]`, de 1 a
64 caracteres) se conserva; si no, se genera un UUID. El mismo identificador aparece en el cuerpo
de los errores y en los logs, que son JSON por línea a stdout (`docker compose logs api`).

Todos los errores usan el formato `{"code", "message", "request_id", "details"}`.

## Verificación en local

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mypy tests
uv run pytest -m "not integration"
```

### Tests de integración (PostgreSQL real)

Necesitan una base de datos. Levanta una temporal con una clave aleatoria que solo vive en tu
terminal:

```bash
export PGPW="$(openssl rand -hex 12)"
docker run --rm -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD="$PGPW" postgres:16
export DATABASE_URL="postgresql+psycopg://postgres:${PGPW}@127.0.0.1:55432/postgres"
uv run pytest -m integration
docker stop pg-test
```

## Migraciones

Alembic está configurado y conectado a la base de datos, sin migraciones de negocio todavía (las
tablas llegan en el incremento 2):

```bash
uv run alembic upgrade head     # con DATABASE_URL definida; termina con éxito sin cambios
```

## Integración continua

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) se ejecuta en cada push a `main` y en cada
pull request, con tres jobs:

1. `quality`: Ruff (lint y formato), mypy y tests unitarios.
2. `integration`: tests contra un PostgreSQL 16 real y `alembic upgrade head`.
3. `compose-smoke`: levanta el entorno con Compose y consulta `/health` y `/ready`.

## Límites conocidos

- La CI informa del resultado pero **no puede bloquear** la integración: comprobado el 2026-11-13,
  GitHub responde 403 («Upgrade to GitHub Pro or make this repository public») al consultar la
  protección de rama de este repositorio privado. Hasta que eso cambie, la regla se cumple por
  proceso: no integrar cambios con la CI en rojo.
- Los tiempos de referencia (`/ready` en unos 3,6 s con la base de datos caída, recuperación en
  1 s) se midieron en una máquina de desarrollo con WSL2 y Docker Desktop; no son garantías.
