# Research: Base del repositorio

Todas las decisiones respetan SPEC §2 y la constitución. No quedan `NEEDS CLARIFICATION`.

## R1. Gestión de dependencias y entorno
- **Decisión:** uv con `pyproject.toml` y `uv.lock` versionado; dependencias de desarrollo en un grupo `dev`; instalación con `uv sync --frozen`.
- **Racional:** exigido por SPEC §2; `--frozen` falla si el lock no coincide (edge case de la spec, SC-007).
- **Alternativas:** pip + requirements (sin lock reproducible), Poetry (no está en el stack).

## R2. Configuración por entorno
- **Decisión:** clase `Settings` con Pydantic v2 (`BaseModel`) cargada por una función propia desde `os.environ`; secretos como `SecretStr`; si la validación falla se captura `ValidationError` y se imprime solo el nombre de variable y el tipo de error, nunca el valor.
- **Racional:** `pydantic-settings` es un paquete aparte y no figura en SPEC §2; añadirlo exigiría aprobación (Principio I, FR-000-17). La carga manual son ≈30 líneas. Los errores por defecto de Pydantic incluyen `input_value`, que podría filtrar secretos, por eso se sanea.
- **Alternativas:** `pydantic-settings` (más cómodo, requiere aprobar la dependencia); python-dotenv (innecesario: Compose inyecta el entorno).
- **Variables:** ver [contracts/environment.md](contracts/environment.md).

## R3. Logging estructurado
- **Decisión:** biblioteca estándar `logging` con un `Formatter` JSON propio (campos `timestamp`, `level`, `logger`, `message`, `request_id`) a stdout, y un `ContextVar` para `request_id`.
- **Racional:** sin dependencias nuevas; stdout es lo que consumen Docker y la CI.
- **Alternativas:** structlog/loguru (dependencia no listada).
- **Notas:** el formateador no serializa `Settings` ni la URL de la base de datos; el log de acceso de Uvicorn se desactiva y lo sustituye un log propio por petición con `request_id`.

## R4. Acceso a PostgreSQL
- **Decisión:** SQLAlchemy 2 con motor síncrono, driver `psycopg` (v3, binario), `connect_timeout=2`, `pool_pre_ping=True`. La sonda `/ready` ejecuta `SELECT 1` en una función `def` de FastAPI (se ejecuta en el pool de hilos y no bloquea el event loop).
- **Racional:** SQLAlchemy 2 y PostgreSQL están fijados; un driver es necesario y `psycopg` 3 es el recomendado por SQLAlchemy 2. Se declara aquí porque no figura con nombre en SPEC §2. El motor síncrono evita complejidad asíncrona innecesaria en este incremento.
- **Alternativas:** asyncpg (otro driver y modelo async), psycopg2 (heredado).
- **Arranque tolerante:** el motor se crea sin conectar (la conexión es perezosa), por lo que el servicio arranca con la base de datos caída (Clarificación 1).

## R5. Identificador de petición
- **Decisión:** middleware ASGI puro (no `BaseHTTPMiddleware`) que lee `X-Request-ID`, lo acepta solo si cumple `^[A-Za-z0-9._-]{1,64}$`, si no genera un UUID4; lo guarda en un `ContextVar` y lo devuelve en la cabecera de respuesta.
- **Racional:** el ASGI puro conserva bien los `ContextVar` y los logs; la lista blanca de caracteres impide inyección de saltos de línea (edge case).
- **Alternativas:** `BaseHTTPMiddleware` (problemas conocidos con contextvars y streaming).

## R6. Errores
- **Decisión:** manejadores globales que devuelven `{code, message, request_id, details}` para `HTTPException`, validación (422), ruta inexistente (404), método no permitido (405) y excepciones no controladas (500, sin trazas ni detalles internos en la respuesta; la traza va al log).
- **Racional:** SPEC §6.2 y FR-000-10.

## R7. Sondas
- **Decisión:** `/health` → 200 `{"status":"ok"}` sin tocar la base de datos. `/ready` → 200 `{"status":"ready","checks":{"database":"ok"}}` o 503 con el sobre de error (`code: "not_ready"`, `details.checks.database: "unavailable"`). Los detalles de la excepción nunca salen en la respuesta.
- **Racional:** FR-000-07/08/09, SPEC §6.2 (`503`); diferido en la clarificación y resuelto aquí.

## R8. Migraciones
- **Decisión:** Alembic con `alembic.ini` en la raíz y entorno en `src/security_anomaly/storage/migrations/`; `env.py` toma la URL de `Settings`; sin revisiones. El comando documentado es `alembic upgrade head`.
- **Racional:** FR-000-19; SPEC §3.1 asigna las migraciones a `storage`.
- **A verificar en implementación:** que `upgrade head` termine con éxito sin revisiones y sin crear tablas de negocio (riesgo del plan).

## R9. Calidad y pruebas
- **Decisión:** Ruff para lint y formato (`ruff check`, `ruff format --check`), mypy en modo estricto, pytest con marcador `integration`; las pruebas HTTP usan el `TestClient` de FastAPI (basado en httpx). Los tests de `/ready` con base de datos caída apuntan a un puerto sin servicio; los de base de datos real leen `DATABASE_URL` del entorno.
- **Racional:** SPEC §2 y NFR-02; separación pedida por FR-000-15.
- **Cobertura mínima:** se difiere (impacto bajo); se medirá sin umbral y se decidirá en un incremento posterior.

## R10. Imagen y Compose
- **Decisión:** Dockerfile multietapa sobre `python:3.12-slim`: etapa de construcción con uv (`uv sync --frozen --no-dev`) y etapa final con el entorno virtual copiado, usuario sin privilegios y `HEALTHCHECK` con Python estándar contra `/health` (sin curl). Compose define `db` (`postgres:16`, `pg_isready`) y `api`; la API depende de `db` solo con `service_started`, para respetar el arranque tolerante. Los puertos se publican en `127.0.0.1` con variables configurables (`API_PORT`); la base de datos no se publica por defecto.
- **Racional:** FR-000-11/12; evita conflictos de puertos (edge case) y exposición innecesaria. La contraseña no tiene valor por defecto en Compose (`${POSTGRES_PASSWORD:?mensaje}`), así que si falta, falla con un mensaje claro.
- **Alternativas:** `depends_on: service_healthy` (haría que la API no arrancase sin base de datos, contra la Clarificación 1); publicar la base de datos (superficie innecesaria).
- **Nota:** la URL de conexión se compone con variables; la contraseña debe ser apta para URL (sin caracteres reservados). Se documenta en `.env.example`.

## R11. CI
- **Decisión:** GitHub Actions con disparadores `push` a `main` y `pull_request`, y tres jobs: `quality` (`uv sync --frozen`, Ruff, mypy, pytest sin integración), `integration` (service container `postgres:16`, pytest `-m integration`, `alembic upgrade head`) y `compose-smoke` (copia `.env.example`, `docker compose up --build --wait`, consulta `/health` y `/ready`, vuelca logs si falla, `down -v`). Acciones fijadas por versión.
- **Racional:** FR-000-13/18, Clarificación 2.
- **Límite:** que los fallos "bloqueen" depende de la protección de rama (ver riesgos del plan).

## R12. Documentación OpenAPI
- **Decisión:** se mantienen `/docs` y `/openapi.json` de FastAPI (SPEC §6) y se versiona un contrato de referencia en `contracts/openapi-probes.yaml`; un test comprueba que el esquema generado contiene `/health` y `/ready`.
