# Quickstart: validar el incremento 2

Guía de validación; no contiene código de implementación. Contratos: [contracts/](contracts/).

## Requisitos previos
- Incrementos 0 y 1 instalados: `uv sync --frozen`.
- Docker con Compose. Una clave de pseudonimización de prueba solo en tu terminal:
  `export PSEUDONYM_KEY="$(openssl rand -hex 32)"`.
- Para los escenarios 2 a 9 se usa una PostgreSQL temporal (no el Compose del proyecto), con una
  clave de administrador aleatoria que solo vive en tu terminal:
  `docker run --rm -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD="$PGPW" postgres:16`.
  Las tres contraseñas de rol (`APP_DB_PASSWORD`, `MAINT_DB_PASSWORD`, `MIGRATOR_DB_PASSWORD`) también
  se generan al vuelo, distintas entre sí, y se construyen las cuatro URL de
  [contracts/environment.md](contracts/environment.md).

## Escenario 1 — Calidad y tests unitarios
1. `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`
2. `uv run pytest -m "not integration"`

**Esperado:** todo pasa sin servicios externos.

## Escenario 2 — Roles y migración (historia 5)
1. `python -m security_anomaly.storage provision-roles` y `alembic upgrade head`.
2. Repetir ambos comandos.

**Esperado:** crean los tres roles y la tabla `events`; repetirlos no cambia nada ni falla. Sin los
roles, `alembic upgrade head` falla con un mensaje que pide aprovisionarlos.

## Escenario 3 — Guardado idempotente (historia 1)
1. Generar 2.000 eventos sintéticos, ingerirlos y guardarlos con `save_events` (rol de aplicación).
2. Guardar el mismo lote otra vez, y luego un lote que solapa con el primero.

**Esperado:** 2.000 insertados; luego 0 insertados y 2.000 existentes; en el solapado, los recuentos
suman correctamente. `SELECT count(*)` no crece. Un fallo forzado a mitad de un lote no deja filas.

## Escenario 4 — Consulta y paginación (historia 2)
1. Combinar filtros de fecha, fuente, resultado, IP y seudónimo; recorrer todas las páginas.
2. Probar parámetros inválidos (`limit` 0 o 5.000, fechas invertidas, IP malformada, un nombre de
   usuario real como filtro).

**Esperado:** conjunción de filtros, cada evento una vez y siempre en el mismo orden con datos
estables; total correcto; los parámetros inválidos se rechazan antes de consultar. Un nombre real
como filtro se rechaza.

## Escenario 5 — Lectura por rango sin fuga de futuro (historia 3)
1. Leer ventanas distintas con `read_range`, incluida una que termina justo en el `timestamp` de un
   evento.

**Esperado:** orden cronológico con desempate fijo, sin duplicados ni saltos, y **ningún evento con
`timestamp >= end`**.

## Escenario 6 — Purga explícita (historia 4)
1. Envejecer filas con el rol migrador (`UPDATE events SET ingested_at = now() - interval '100 days'`).
2. `python -m security_anomaly.storage purge --dry-run`, después `purge`, después `purge` otra vez.
3. Ejecutar `purge --days 0`.

**Esperado:** la simulación informa cuántos y no borra; la purga real borra esos; la repetición borra 0;
`--days 0` se rechaza con salida 2 sin borrar. Nada se purga solo.

## Escenario 7 — Privilegios (historia 5, SC-007)
1. Con el rol de aplicación: `INSERT` y `SELECT` funcionan; `DELETE`, `TRUNCATE`, `UPDATE`,
   `CREATE TABLE` y `DROP TABLE` fallan con permiso denegado.
2. Con el rol de mantenimiento: `DELETE` funciona; `INSERT` y DDL fallan.

**Esperado:** coincide con la tabla de [contracts/operations.md](contracts/operations.md).

## Escenario 8 — Entorno Compose (historia 5)
1. `cp .env.example .env` y sustituir las cuatro contraseñas por valores aleatorios distintos.
2. `docker compose up --build -d --wait` → `/health` 200 y `/ready` 503.
3. `docker compose --profile setup run --rm db-setup` → `/ready` 200.
4. `docker compose --profile maintenance run --rm db-maintenance` → informa de la simulación.

**Esperado:** la base de datos sigue sin publicarse en el equipo y la API usa el rol de aplicación.

## Escenario 9 — Rotación de clave (historia 6)
1. Ingerir un `auth.log` con la clave A y guardar; ingerir el mismo archivo con la clave B y guardar.

**Esperado:** los identificadores y seudónimos cambian, así que se inserta de nuevo (no es
idempotente). Con el procedimiento del [ADR 0003](../../docs/decisions/0003-rotacion-pseudonym-key.md)
(purgar antes de rotar) solo quedan los eventos con la clave nueva.

## Escenario 10 — Rendimiento
1. Guardar 10.000 eventos (SC-001) y medir; cargar 100.000 y consultar un día (SC-004), comprobando
   con `EXPLAIN` que se usa el índice de `timestamp`.

**Esperado:** menos de 10 s y menos de 1 s; registrar los tiempos reales.
