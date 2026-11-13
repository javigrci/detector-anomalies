# Quickstart: validar el incremento 0

Guía de validación; no contiene código de implementación. Contratos: [contracts/](contracts/).

## Requisitos previos
- Linux o WSL2 con `uv` instalado.
- Docker con Compose. En WSL2 con Docker Desktop, activa la integración con esta distro
  (Settings → Resources → WSL integration).

## Escenario 1 — Calidad en local (historia 3)
1. `uv sync --frozen`
2. `uv run ruff check . && uv run ruff format --check .`
3. `uv run mypy src tests`
4. `uv run pytest -m "not integration"`

**Esperado:** todo pasa. Introducir un error de estilo, de tipos o un test fallido hace fallar el paso correspondiente.

## Escenario 2 — Arranque completo (historia 1)
1. `cp .env.example .env` y poner una `POSTGRES_PASSWORD` apta para URL.
2. `docker compose up --build -d --wait`
3. `curl -i http://127.0.0.1:8000/health` → 200 `{"status":"ok"}`.
4. `curl -i http://127.0.0.1:8000/ready` → 200 `{"status":"ready","checks":{"database":"ok"}}`.

## Escenario 3 — Base de datos caída (historia 2, SC-005)
1. `docker compose stop db`
2. `/health` → 200; `/ready` → 503 con `code: "not_ready"` en menos de 5 s.
3. `docker compose start db` → `/ready` vuelve a 200 en menos de 30 s, sin reiniciar la API.

## Escenario 4 — Arranque sin base de datos (Clarificación 1)
1. `docker compose down`, luego `docker compose up -d --no-deps --build api` (sin `--no-deps`, Compose arrancaría también `db`).
2. La API arranca; `/health` 200 y `/ready` 503.

## Escenario 5 — Trazabilidad (historia 4)
1. `curl -i -H 'X-Request-ID: abc-123' .../health` → la respuesta devuelve `X-Request-ID: abc-123`.
2. Sin cabecera → se devuelve un UUID. Con `X-Request-ID` inválido (espacios, >64 caracteres) → se sustituye por un UUID.
3. `docker compose logs api` → líneas JSON con el mismo `request_id`, sin secretos.

## Escenario 6 — Configuración inválida (historia 1, FR-000-03)
1. Arrancar el servicio sin `DATABASE_URL`.
2. **Esperado:** termina con error que nombra `DATABASE_URL` y no muestra ningún valor.

## Escenario 7 — Migraciones (FR-000-19)
1. `uv run alembic upgrade head` con la base de datos en marcha → termina con éxito; no existen tablas de negocio.

## Escenario 8 — CI
1. Abrir un cambio y comprobar que se ejecutan los jobs `quality`, `integration` y `compose-smoke`.
2. Provocar un fallo en cada uno y comprobar que se marca en rojo.
