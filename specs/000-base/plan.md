# Implementation Plan: Base del repositorio

**Branch**: `000-base` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/000-base/spec.md`

## Summary

Esqueleto ejecutable del proyecto: servicio FastAPI mínimo con `/health` y `/ready`, configuración
por entorno validada al arrancar, logging JSON con `request_id`, errores con formato único,
herramienta de migraciones conectada pero sin migraciones, imagen Docker y Compose (API +
PostgreSQL 16), y CI con lint, formato, tipos, tests unitarios, tests con PostgreSQL real y prueba
de humo de Compose. Sin lógica de negocio. Decisiones y alternativas en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (gestionado con uv; `requires-python = ">=3.12,<3.13"`)

**Primary Dependencies** (todas de SPEC §2; versiones exactas las fija `uv.lock`):
FastAPI, Pydantic v2, Uvicorn, SQLAlchemy 2, Alembic y el driver `psycopg` (v3), implícito en
"PostgreSQL" y justificado en research R4. Desarrollo: pytest, httpx, Ruff, mypy. Construcción: backend de uv (`uv_build`). CI: acciones `actions/checkout` y `astral-sh/setup-uv`. Estas tres adiciones y el driver se registran en `docs/decisions/0002-dependencias-base.md`. Se deja fuera
`pydantic-settings` (no está en SPEC §2; ver R2).

**Storage**: PostgreSQL 16 vacío (solo se verifica conectividad; sin tablas de negocio)

**Testing**: pytest con marcador `integration` para lo que exige PostgreSQL real; el resto es unitario sin servicios externos

**Target Platform**: Linux (contenedor); desarrollo en Linux/WSL2

**Project Type**: web-service (API REST), un único proyecto Python

**Performance Goals**: metas orientativas de la spec: `/health` < 30 s y `/ready` < 60 s tras el arranque (SC-002); sin objetivos de rendimiento adicionales en este incremento

**Constraints**: arranque tolerante a base de datos caída (Clarificación 1); timeout de conexión a la base de datos acotado (2 s) para que `/ready` no se cuelgue; ningún secreto en imagen, logs ni Git; contenedor sin root

**Scale/Scope**: ≈15 archivos fuente, 8 paquetes, 3 jobs de CI; sin carga ni volumen de datos

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Spec como fuente de verdad | Cada tarea será trazable a FR-000-xx; sin endpoints ni dependencias fuera de SPEC §2 (el driver `psycopg` se declara en R4) | ✅ |
| II. Honestidad en la detección | No hay scoring ni ML en este incremento | ✅ (N/A) |
| III. Integridad del ML | No hay ML | ✅ (N/A) |
| IV. Seguridad y privacidad | Secretos solo por entorno, `SecretStr`, errores de configuración sin valores, `request_id` saneado, contenedor sin root, sin secretos en la imagen | ✅ |
| V. Test-first | Los tests de cada tarea se escriben antes y fallan primero; Ruff, mypy y pytest en CI | ✅ |
| VI. Reproducibilidad | `uv.lock`, Compose de un comando, Alembic conectado, decisiones en `docs/decisions/` | ✅ |
| VII. Humano en el circuito / alcance mínimo | Solo lo especificado; sin autenticación, ingesta ni ML | ✅ |

**Post-diseño:** sin cambios; sin violaciones, por lo que no hay entradas en Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/000-base/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi-probes.yaml      # /health, /ready y el sobre de error
│   └── environment.md           # variables de entorno
├── checklists/requirements.md
└── tasks.md                     # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
pyproject.toml · uv.lock · .env.example · Dockerfile · compose.yaml · alembic.ini · README.md
.dockerignore
.github/workflows/ci.yml
src/security_anomaly/
├── __init__.py
├── api/
│   ├── __init__.py
│   ├── main.py            # create_app(): middleware, handlers, routers
│   ├── errors.py          # sobre de error y manejadores globales
│   └── routes/health.py   # /health y /ready
├── core/
│   ├── __init__.py
│   ├── config.py          # Settings y carga desde entorno
│   ├── logging.py         # formateador JSON y configuración
│   └── request_id.py      # middleware ASGI y contextvar
├── storage/
│   ├── __init__.py
│   ├── database.py        # motor SQLAlchemy y ping
│   └── migrations/        # entorno Alembic (sin revisiones)
├── ingestion/ · features/ · ml/ · scoring/ · schemas/   # solo __init__.py
tests/
├── unit/                  # config, logging, request_id, errores, health/ready sin DB
├── integration/           # ready con PostgreSQL real; alembic
└── conftest.py
```

**Structure Decision**: proyecto único con layout `src/` (SPEC §3.2). `storage/migrations/`
alberga Alembic porque SPEC §3.1 asigna las migraciones a `storage`. `dashboard/`, `docs/` y
`scripts/` se crean cuando haya contenido.

## Fases de entrega (orden previsto para `/speckit-tasks`)

El orden vigente es el de [tasks.md](tasks.md), que prevalece sobre esta lista:

1. **Cimientos (Setup):** ADR de dependencias, `pyproject.toml`, estructura de paquetes, herramientas de calidad (Ruff, mypy, pytest) y primer test que pase.
2. **Fundamentos (Foundational):** `Settings`, formateador JSON, sobre de error y `create_app()`.
3. **Sondas (US2):** motor de base de datos, `/health` y `/ready`, comportamiento con base de datos caída.
4. **Entorno completo (US1):** entrypoint, Alembic conectado, `.env.example`, Dockerfile y Compose.
5. **Trazabilidad (US4):** middleware de `request_id` y log por petición.
6. **CI (US3):** workflow con los tres jobs, commit y push con autorización.
7. **Documentación (US5):** README y verificación en un clon limpio.
8. **Cierre:** evidencia, búsqueda de secretos y revisión final contra la spec.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| `docker` no disponible en esta distro de WSL (Docker Desktop sin integración activada) | Activar la integración WSL en Docker Desktop; si no, validar Compose en la CI y declarar en el cierre que no se probó en local |
| "Bloquea la integración" (FR-000-13/18) exige protección de rama; en repositorios privados de planes gratuitos puede no estar disponible | Verificar en los ajustes del repositorio; si no, documentarlo como limitación y hacer cumplir la regla por proceso |
| `alembic upgrade head` sin revisiones podría no comportarse como se espera | Verificarlo en la tarea de Alembic con un test de integración antes de documentarlo |
| `/ready` lento si la base de datos no responde | Timeout de conexión de 2 s y prueba que lo comprueba |

## Complexity Tracking

Sin violaciones de la constitución; no aplica.
