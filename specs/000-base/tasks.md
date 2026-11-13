---

description: "Tareas del incremento 0 — Base del repositorio"
---

# Tasks: Base del repositorio

**Input**: Documentos de diseño en `/specs/000-base/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: OBLIGATORIOS (Constitución, Principio V). Cada historia incluye primero sus tareas de test; se escriben y se confirma que FALLAN antes de implementar.

**Organization**: Tareas agrupadas por historia de usuario. Las historias US1 y US2 son ambas P1; se ejecuta US2 antes porque la prueba de arranque de US1 necesita `/health`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1…US5)
- Cada tarea cita requisitos (FR-000-xx) y rutas exactas

## Notas de ejecución

- Se trabaja en `main`; los commits y pushes (T040 y T047) requieren autorización explícita (Principio VII).
- Los tests marcados `integration` necesitan PostgreSQL real. En local, levantar uno temporal: `docker run --rm -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=<clave-local> postgres:16` y exportar `DATABASE_URL` hacia él (la clave solo en el entorno, nunca en Git). En la CI lo aporta un service container.
- Las versiones exactas de dependencias y de acciones de GitHub se resuelven al implementar (`uv lock`, consulta de versiones reales); no se inventan.
- Los resultados de cada tarea de verificación se registran tal como salen (Principio V).

---

## Phase 1: Setup (infraestructura compartida)

**Purpose**: proyecto instalable y herramientas de calidad en verde con un primer test.

- [X] T001 Registrar en `docs/decisions/0002-dependencias-base.md` las decisiones aprobadas sobre dependencias: uso de `psycopg` (v3), no usar `pydantic-settings`, backend de construcción de uv (`uv_build`, solo herramienta de construcción) y acciones de GitHub de terceros de la CI (`actions/checkout`, `astral-sh/setup-uv`); con contexto y alternativas (ref. research R1, R2, R4 y R11; FR-000-17)
- [X] T002 Crear `pyproject.toml`: metadatos, `requires-python = ">=3.12,<3.13"`, dependencias (fastapi, pydantic>=2, uvicorn, sqlalchemy>=2, alembic, psycopg[binary]), grupo `dev` (pytest, httpx, ruff, mypy), backend de construcción de uv con layout `src/`, configuración de Ruff, mypy estricto y pytest (marcador `integration`, `testpaths = ["tests"]`) (FR-000-01, FR-000-13)
- [X] T003 Generar `uv.lock` con `uv lock` y comprobar `uv sync --frozen` en limpio (FR-000-01, SC-007)
- [X] T004 [P] Escribir `tests/unit/test_package_structure.py` y `tests/conftest.py`: importa los 8 paquetes de `security_anomaly` (`api`, `core`, `ingestion`, `features`, `ml`, `scoring`, `storage`, `schemas`) (FR-000-02); confirmar que falla
- [X] T005 Crear `src/security_anomaly/__init__.py`, `py.typed` y los `__init__.py` de los 8 subpaquetes, sin lógica de negocio (FR-000-02, FR-000-17)
- [X] T006 Ejecutar `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src tests` y `uv run pytest -m "not integration"`; todo en verde (FR-000-13)

---

## Phase 2: Foundational (bloquea todas las historias)

**Purpose**: configuración, logging, errores y la fábrica de la aplicación.

**⚠️ CRITICAL**: ninguna historia empieza hasta terminar esta fase.

### Tests (escribir primero; deben fallar)

- [X] T007 [P] Escribir `tests/unit/test_config.py`: valores por defecto, `DATABASE_URL` obligatoria, vacío = ausente, enums y rangos inválidos, esquema `postgresql+psycopg://`, `SecretStr` ausente de `repr`/`str`, y mensaje de error que nombra la variable sin mostrar el valor (FR-000-03, data-model Settings)
- [X] T008 [P] Escribir `tests/unit/test_logging.py`: una línea JSON por registro con `timestamp` (UTC ISO 8601), `level`, `logger`, `message`, `request_id` cuando existe; no serializa secretos; respeta `LOG_LEVEL` (FR-000-05)
- [X] T009 [P] Escribir `tests/unit/test_errors.py`: 404, 405, 422 y 500 devuelven `{code, message, request_id, details}`; el 500 no expone traza ni detalles internos (FR-000-10)

### Implementación

- [X] T010 Implementar `src/security_anomaly/core/config.py`: `Settings` (Pydantic v2 `BaseModel`) y `load_settings()` desde `os.environ`, con saneo de `ValidationError` (research R2; contracts/environment.md) (T007)
- [X] T011 [P] Implementar solo el `ContextVar` `request_id_var` en `src/security_anomaly/core/request_id.py`; la validación del identificador y el middleware se implementan en T035, después de sus tests (research R5)
- [X] T012 Implementar `src/security_anomaly/core/logging.py`: formateador JSON a stdout y `configure_logging(level)`; lee `request_id_var` (research R3) (T008, T011)
- [X] T013 [P] Implementar `src/security_anomaly/api/errors.py`: modelo del sobre de error y manejadores globales (research R6) (T009)
- [X] T014 Implementar `src/security_anomaly/api/main.py` con `create_app(settings: Settings | None = None)`: configura logging, registra manejadores de error; sin rutas de negocio (T010, T012, T013)
- [X] T015 Ejecutar T007–T009 y confirmar que pasan; Ruff y mypy en verde

**Checkpoint**: configuración, logging y errores listos; las historias pueden empezar.

---

## Phase 3: User Story 2 — Comprobar el estado del servicio (Priority: P1) 🎯

**Goal**: `/health` y `/ready` según el contrato, con arranque tolerante a la base de datos caída.

**Independent Test**: con la base de datos disponible y con una inaccesible, comparar las respuestas de las dos sondas.

### Tests (escribir primero; deben fallar)

- [X] T016 [P] [US2] Escribir `tests/unit/test_health.py`: `/health` devuelve 200 `{"status":"ok"}` sin tocar la base de datos (con URL inaccesible), sin credenciales y fuera de `/api/v1` (FR-000-07, FR-000-09)
- [X] T017 [P] [US2] Escribir `tests/unit/test_ready.py`: con base de datos inaccesible `/ready` devuelve 503 con `code: "not_ready"` y `details.checks.database: "unavailable"`, sin detalles de la excepción; el motor se construye con `connect_timeout` igual a `DB_CONNECT_TIMEOUT_S` (comprobando los argumentos de conexión, no el tiempo real, para que el test sea determinista); la aplicación se crea y arranca con la base de datos caída (FR-000-08, Clarificación 1). El tiempo real (menos de 5 s) se mide en T032 (SC-005)
- [X] T018 [P] [US2] Escribir `tests/integration/test_ready_db.py` (marcador `integration`): con PostgreSQL real `/ready` devuelve 200 `{"status":"ready","checks":{"database":"ok"}}` (FR-000-08)
- [X] T019 [P] [US2] Escribir `tests/unit/test_openapi_contract.py`: el esquema generado contiene `/health` y `/ready` con las respuestas de `contracts/openapi-probes.yaml` (research R12)

### Implementación

- [X] T020 [US2] Implementar `src/security_anomaly/storage/database.py`: `create_db_engine(settings)` perezoso (`connect_timeout`, `pool_pre_ping`) y `check_database(engine) -> bool` que captura la excepción y registra solo su tipo (research R4)
- [X] T021 [US2] Implementar `src/security_anomaly/api/routes/health.py` (`/health` y `/ready` como funciones `def`) y registrarlo en `create_app` (research R7) (T020)
- [X] T022 [US2] Ejecutar T016–T019 (los de integración contra el PostgreSQL temporal de las notas) y confirmar que pasan

**Checkpoint**: sondas funcionando y verificadas de forma independiente.

---

## Phase 4: User Story 1 — Levantar el entorno completo desde cero (Priority: P1)

**Goal**: un solo comando arranca la API y PostgreSQL 16; configuración inválida falla con mensaje claro; migraciones conectadas.

**Independent Test**: en un clon limpio, copiar `.env.example` y ejecutar `docker compose up --build`; `/health` y `/ready` responden sin pasos adicionales.

**Depende de**: US2 (necesita `/health` y `/ready`).

### Tests (escribir primero; deben fallar)

- [X] T023 [P] [US1] Escribir `tests/unit/test_main_entrypoint.py`: `python -m security_anomaly` sin `DATABASE_URL` termina con código distinto de 0, el error nombra `DATABASE_URL` y no contiene el valor de ninguna variable proporcionada (FR-000-03)
- [X] T024 [P] [US1] Escribir `tests/integration/test_alembic.py` (marcador `integration`): `alembic upgrade head` termina con éxito contra PostgreSQL real y no crea tablas de negocio (FR-000-19, FR-000-17)
- [X] T025 [P] [US1] Escribir `tests/unit/test_repo_hygiene.py`: `.env.example` contiene todas las variables de `contracts/environment.md` y ningún secreto real; `.gitignore` excluye `.env`; el `Dockerfile` define un usuario sin privilegios y no declara secretos en `ENV`/`ARG` (FR-000-04, FR-000-12)

### Implementación

- [X] T026 [US1] Implementar `src/security_anomaly/__main__.py`: carga `Settings` (error saneado y salida con código 2), configura logging y arranca Uvicorn con la fábrica, en el puerto de `API_PORT`, sin log de acceso propio de Uvicorn (FR-000-03) (T023)
- [X] T027 [US1] Crear `alembic.ini` y `src/security_anomaly/storage/migrations/` (`env.py` que toma la URL de `Settings`, `script.py.mako`, `versions/.gitkeep`), sin revisiones (FR-000-19, research R8) (T024)
- [X] T028 [P] [US1] Crear `.env.example` con todas las variables de `contracts/environment.md`, valores de desarrollo y sin secretos reales; verificar que `.env` está en `.gitignore` (FR-000-04)
- [X] T029 [P] [US1] Crear `.dockerignore` (excluye `.git`, `.env`, `.venv`, cachés, `tests/`, `specs/`, `.specify/`, `.claude/`)
- [X] T030 [US1] Crear `Dockerfile` multietapa sobre `python:3.12-slim`: construcción con `uv sync --frozen --no-dev`, entorno virtual copiado, usuario sin privilegios, `HEALTHCHECK` con Python estándar contra `/health`, `CMD ["python","-m","security_anomaly"]`; el `HEALTHCHECK` lee el puerto de la variable `API_PORT` (no lo fija) (FR-000-11, FR-000-12; research R10) (T026)
- [X] T031 [US1] Crear `compose.yaml`: servicio `db` (`postgres:16`, `pg_isready`, volumen), servicio `api` (build local, `env_file`, `DATABASE_URL` compuesta, `depends_on` solo `service_started`, puerto publicado como `127.0.0.1:${API_PORT:-8000}:${API_PORT:-8000}` para que host y contenedor usen el mismo valor), `POSTGRES_PASSWORD` obligatoria con `${POSTGRES_PASSWORD:?mensaje}`; la base de datos no se publica (FR-000-11; research R10) (T028, T030)
- [X] T032 [US1] Verificar quickstart escenarios 2, 3, 4, 6 y 7 con Docker real: `up --build -d --wait`, `/health` y `/ready`; `stop db` → 503 en menos de 5 s; `start db` → 200 en menos de 30 s; API sin `db`; arranque sin `DATABASE_URL`; `alembic upgrade head`. Comprobaciones adicionales: el proceso del contenedor no es root (`docker compose exec api id -u` distinto de 0); `docker image inspect` no muestra variables sensibles (`DATABASE_URL`, `POSTGRES_PASSWORD`) en la imagen; con `API_PORT=9000` el servicio y su `HEALTHCHECK` funcionan; con el puerto ocupado por otro proceso, el arranque falla con un mensaje claro y el cambio de `API_PORT` lo resuelve. Registrar tiempos y resultados reales (FR-000-12, SC-001, SC-002, SC-005)

**Checkpoint**: entorno completo reproducible.

---

## Phase 5: User Story 4 — Trazar cada petición en los logs (Priority: P2)

**Goal**: `request_id` en cada respuesta y en cada registro de la petición.

**Independent Test**: enviar peticiones con y sin identificador y comprobar cabecera y logs.

### Tests (escribir primero; deben fallar)

- [X] T033 [P] [US4] Escribir `tests/unit/test_request_id_middleware.py`: genera UUID cuando falta; conserva uno válido; sustituye uno inválido (espacios, más de 64 caracteres, saltos de línea, vacío); la cabecera `X-Request-ID` aparece en toda respuesta, incluidas 404, 422 y 500; el `ContextVar` se restablece tras la petición (FR-000-06, SC-004)
- [X] T034 [P] [US4] Escribir `tests/unit/test_request_logging.py`: cada petición emite una línea JSON con el mismo `request_id` que la cabecera y el sobre de error; no se registran cabeceras `Authorization`/`Cookie` ni la URL de la base de datos (FR-000-05, FR-000-06)

### Implementación

- [X] T035 [US4] En `src/security_anomaly/core/request_id.py` implementar `is_valid_request_id()` (`^[A-Za-z0-9._-]{1,64}$`), `RequestIdMiddleware` (ASGI puro) y el log por petición; registrarlo en `create_app` de `src/security_anomaly/api/main.py` (research R5) (T033, T034)
- [X] T036 [US4] Verificar quickstart escenario 5 contra el entorno Compose y revisar `docker compose logs api` en busca de secretos

**Checkpoint**: trazabilidad verificada.

---

## Phase 6: User Story 3 — Verificar calidad automáticamente (Priority: P2)

**Goal**: lint, formato, tipos, tests, tests con PostgreSQL real y prueba de humo de Compose en CI, con las mismas comprobaciones disponibles en local.

**Independent Test**: provocar un error de estilo, de tipos y un test fallido; cada uno rompe la verificación; con el código correcto, pasa.

### Tests (escribir primero; deben fallar)

- [X] T037 [P] [US3] Escribir `tests/unit/test_ci_workflow.py` con comprobaciones de texto (sin dependencia YAML): existen los jobs `quality`, `integration` y `compose-smoke`; disparadores `push` a `main` y `pull_request`; usa `uv sync --frozen`; el job de integración define un service container `postgres:16`; el humo ejecuta `docker compose up --build` y consulta `/health` y `/ready` (FR-000-13, FR-000-18)

### Implementación

- [X] T038 [US3] Crear `.github/workflows/ci.yml` con los tres jobs de research R11; acciones fijadas por versión real consultada; volcado de logs de Compose si falla y `down -v` al final (FR-000-13, FR-000-18) (T037)
- [X] T039 [US3] Verificar en local quickstart escenario 1 y los fallos provocados: un error de Ruff, uno de mypy y un test fallido rompen cada paso (código de salida distinto de 0); `uv lock --check` falla con un lock desactualizado; revertir todo lo provocado (SC-003, SC-007)
- [ ] T040 [US3] **Requiere autorización del usuario (commit y push):** hacer commit del trabajo realizado hasta esta tarea (sin `.env` ni secretos) y subirlo a GitHub; observar la ejecución real de los tres jobs; comprobar con `gh api` si el repositorio permite protección de rama; documentar el resultado y, si no está disponible, la limitación en `README.md` (riesgo 2 del plan)

**Checkpoint**: puerta de calidad automática operativa.

---

## Phase 7: User Story 5 — Orientarse en la estructura del proyecto (Priority: P3)

**Goal**: estructura acordada y README que permite arrancar, verificar y detener sin información adicional.

**Independent Test**: seguir el README en un clon limpio y comprobar cada comando.

### Tests (escribir primero; deben fallar)

- [X] T041 [P] [US5] Escribir `tests/unit/test_readme.py`: el README existe y menciona los comandos `uv sync --frozen`, `docker compose up --build`, `alembic upgrade head`, `/health`, `/ready` y la variable `POSTGRES_PASSWORD` (FR-000-16)

### Implementación

- [X] T042 [US5] Escribir `README.md`: requisitos (uv, Docker con integración WSL), instalación, configuración (`.env`), arranque, verificación local (Ruff, mypy, pytest, PostgreSQL temporal para integración), sondas, migraciones, detención, CI y límites conocidos (FR-000-16) (T041)
- [ ] T043 [US5] Clonar el repositorio en un directorio nuevo del scratchpad y seguir el README al pie de la letra; anotar tiempos y cualquier paso que falte, y corregir el README (SC-001)

**Checkpoint**: todas las historias completas y verificadas.

---

## Phase 8: Polish y cierre

**Purpose**: evidencia, revisión y cierre del incremento.

- [ ] T044 Crear `specs/000-base/verification.md`: resultados reales de los 8 escenarios de `quickstart.md`, tabla FR-000-01…19 y SC-001…007 con evidencia, y desviaciones respecto al plan
- [ ] T045 [P] Búsqueda de secretos en el árbol de trabajo y en el historial (`git log -p`, patrones de claves y contraseñas) y comprobar que `.env` no está versionado (SC-006)
- [ ] T046 [P] Ejecutar la verificación completa final: Ruff, formato, mypy, pytest con y sin `integration`, `docker compose up --build -d --wait`, `down -v`; informar de los resultados tal como salgan (NFR-02)
- [ ] T047 Revisar los criterios de aceptación uno a uno y el Constitution Check del plan; comprobar que `pyproject.toml` y el OpenAPI generado no contienen dependencias ni rutas fuera de la spec y SPEC §2 (FR-000-17); proponer el mensaje de commit de cierre y **pedir autorización** antes de hacer commit y push (Principio VII; Definition of Done)

---

## Dependencies & Execution Order

### Orden de fases

- **Setup (1)** → **Foundational (2)** → resto de historias.
- **US2 (3)** → **US1 (4)** → **US4 (5)** → **US3 (6)** → **US5 (7)** → **Polish (8)**.
- US4 va antes que US3 porque la CI (`compose-smoke`) debe validar el servicio completo; US5 al final porque el README documenta lo ya construido.

### Dependencias entre historias

- **US2**: solo depende de Foundational.
- **US1**: depende de US2 (`/health` y `/ready`) y de la configuración.
- **US4**: depende de Foundational (`create_app`, `request_id_var`); verificable con US1 en Compose.
- **US3**: depende de US1 (Compose) para el humo y de las pruebas existentes.
- **US5**: depende de todas.

### Dentro de cada historia

Tests (fallan) → implementación → verificación. Las tareas de test [P] de una misma historia son paralelas entre sí.

### Oportunidades de paralelismo

- Setup: T004 en paralelo con la preparación de T002/T003 una vez creado el árbol.
- Foundational: T007, T008, T009 juntos; T011 y T013 en paralelo con T010.
- US2: T016, T017, T018, T019 juntos.
- US1: T023, T024, T025 juntos; T028 y T029 juntos.
- US4: T033 y T034 juntos.
- Polish: T045 y T046 juntos.

### Ejemplo de paralelismo (US2)

```text
T016 tests/unit/test_health.py
T017 tests/unit/test_ready.py
T018 tests/integration/test_ready_db.py
T019 tests/unit/test_openapi_contract.py
```

---

## Implementation Strategy

### Entrega mínima (US2 → US1)

1. Setup + Foundational.
2. US2: sondas verificadas de forma independiente.
3. US1: el servicio arranca con un comando. **PARAR y validar** la puerta de aceptación principal del incremento (`docker compose up --build` + tests mínimos).

### Entrega incremental

4. US4 (trazabilidad) → 5. US3 (CI) → 6. US5 (README) → 7. Polish.

### Criterio de cierre

El incremento está terminado solo si T044–T047 se completan con evidencia real, pytest, Ruff y mypy pasan y no hay secretos versionados. Si algún criterio falla, no se declara terminado (Principio V).
