# Verificación del incremento 2 — Persistencia de eventos

**Fecha:** 2026-11-22 · **Estado:** implementación completa y verificada en local; **CI de GitHub pendiente**
(se ejecutará al hacer push, T069). Todos los resultados de este documento son salidas reales.

## 1. Puertas de calidad (T065)

| Comprobación | Resultado |
|---|---|
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `183 files already formatted` |
| `uv run mypy` (estricto, `src`) | `Success: no issues found in 41 source files` |
| `uv run mypy tests` | `Success: no issues found in 87 source files` |
| `uv run pytest -q -m "not integration"` | **490 passed**, 109 deselected |
| `uv run pytest -q -m integration` (PostgreSQL 16 real) | **109 passed**, 490 deselected |

Total: **599 tests** (antes del incremento: 329 unitarios + 2 de integración). Un aviso heredado
(`starlette.testclient` con `httpx`) sigue igual que en el incremento 1.

Entorno de las mediciones: Linux 6.6.87.2 (WSL2), 12 CPU, Python 3.12.15, PostgreSQL 16 en un
contenedor local con configuración por defecto, Docker Desktop. No son garantías de rendimiento.

## 2. Criterios de éxito

| SC | Resultado | Evidencia |
|---|---|---|
| SC-001 | ✅ 10.000 eventos guardados en **2,339 s** (umbral 10 s). Reguardar el mismo lote (todo existente): 4,040 s | `test_perf_save.py` |
| SC-002 | ✅ 0 filas nuevas al reguardar, también con 8 y 6 hilos concurrentes | `test_save_idempotent.py`, `test_save_concurrent.py` |
| SC-003 | ✅ 5.000 eventos con páginas de 100: cada uno una vez y mismo orden en dos recorridos | `test_query_pagination.py` |
| SC-004 | ✅ Un día (3.333 eventos) sobre 100.000: **0,083 s** (umbral 1 s); el plan usa `ix_events_timestamp` y no hay `Seq Scan` | `test_perf_query.py` |
| SC-005 | ✅ Tras la purga no queda nada más antiguo que el periodo; lo reciente, aunque con timestamps antiguos, permanece; la simulación no borra | `test_purge.py` |
| SC-006 | ✅ 0 apariciones de usuario, contraseñas o valores sentinela en datos, resultados, errores, logs y salida de la CLI | `test_no_leaks.py`, `test_no_username_stored.py` |
| SC-007 | ✅ Todos los intentos prohibidos con el rol de aplicación y el de mantenimiento son denegados (SQLSTATE 42501) y el estado real no cambia | `test_privileges.py` |
| SC-008 | ✅ Migración sobre base vacía y de nuevo sobre la ya migrada sin errores; el ADR 0003 existe y cubre los tres efectos | `test_alembic.py`, `test_adr_rotation.py` |

## 3. Escenarios de `quickstart.md`

| Escenario | Resultado |
|---|---|
| 1. Calidad y unitarios | ✅ sección 1 |
| 2. Roles y migración | ✅ Manual contra PostgreSQL temporal: `provision-roles` dos veces (`{"command": "provision-roles", "roles": 3}`), `alembic upgrade head` dos veces, tablas `events` y `alembic_version`. Sin `MIGRATION_DATABASE_URL`: `ConfigError … MIGRATION_DATABASE_URL: obligatoria`. El mensaje de roles ausentes se prueba a nivel de función (ver §5) |
| 3. Guardado idempotente | ✅ tests de integración |
| 4. Consulta y paginación | ✅ tests de integración (incluye parámetros inválidos y un nombre real como filtro) |
| 5. Rango sin fuga de futuro | ✅ `test_read_range*.py`, con una ventana que termina justo en el `timestamp` de un evento |
| 6. Purga | ✅ Manual con 7 filas envejecidas: `--dry-run` → `affected 7` y siguen 7; `--days 0` → salida **2**, siguen 7; `purge` → `affected 7`; repetir → `affected 0`; quedan 0 |
| 7. Privilegios | ✅ `test_privileges.py` |
| 8. Compose | ✅ ver §4 |
| 9. Rotación de clave | ✅ `test_key_rotation.py` |
| 10. Rendimiento | ✅ SC-001 y SC-004 |

## 4. Compose en local (T057)

Con un `.env` temporal de contraseñas aleatorias distintas (borrado después):

1. `docker compose up --build -d --wait` → `/health` **200**, `/ready` **503**.
2. `docker compose --profile setup run --rm db-setup` → `{"command": "provision-roles", "roles": 3}`;
   después `/ready` **200** con el rol `anomaly_app`.
3. `docker compose --profile maintenance run --rm db-maintenance` → simulación (`dry_run: true`, `affected: 0`).
   `… purge --dry-run` y `… purge` (real) funcionan; `purge --days 0` → `--days debe ser al menos 1`.
4. `docker compose ps`: la base de datos muestra `5432/tcp` **sin** publicar en el host; la API solo en `127.0.0.1:8000`.
5. `docker compose down -v` limpia todo.

## 5. Matriz de requisitos

| Requisitos | Tareas | Tests principales |
|---|---|---|
| FR-002-01…06 | T008–T011, T016–T018, T021, T025 | `test_schema.py`, `test_storage_models.py`, `test_alembic.py`, `test_no_username_stored.py` |
| FR-002-07…12 | T021–T029 | `test_save_*.py` |
| FR-002-13…17 | T030–T042 | `test_query_*.py`, `test_read_range*.py` |
| FR-002-18 | T010, T018, T040 | `test_schema.py`, `test_perf_query.py` (plan con índice) |
| FR-002-19…21 | T043–T051 | `test_retention_logic.py`, `test_purge*.py`, `test_cli.py` |
| FR-002-22…23 | T002–T003, T012–T013, T052–T057 | `test_privileges.py`, `test_provision_roles.py`, `test_compose_config.py` |
| FR-002-24…26 | T005, T007, T026, T030, T034, T048, T062 | `test_errors.py`, `test_query_build.py`, `test_*_logging.py`, `test_no_leaks.py` |
| FR-002-27 | T014, T058–T060 | ADR 0003, `test_key_rotation.py`, `test_adr_rotation.py` |
| FR-002-28 | T015, T020, T056, T067 | CI actualizada (sin ejecutar aún en GitHub) |
| FR-002-29 | T067 | sin dependencias, endpoints ni tablas de modelo (ver §6) |

Las pruebas que pasaban sin código nuevo se comprobaron con mutación: dar `DELETE` al rol de aplicación en
la migración hace fallar `test_privileges.py` (restaurado después).

## 6. Alcance (T067)

- `git diff -- pyproject.toml uv.lock`: vacío → **sin dependencias nuevas**.
- Sin `APIRouter` ni endpoints nuevos; sin tablas de predicciones, versiones de modelo o entrenamiento.
- Sin secretos en el diff; `.env` no existe en el árbol (se creó y se borró durante T057).

## 7. Desviaciones y limitaciones (dichas tal como son)

1. **Fixtures de integración en `tests/integration/conftest.py`**, no en `tests/integration/storage/conftest.py`
   (T015): `test_alembic.py` vive un nivel por encima y las comparte. En `storage/conftest.py` solo queda
   el vaciado de `events` entre tests.
2. **Autenticación `trust`:** la base de datos de pruebas (y la de la CI) no valida contraseñas, así que el test
   de rotación de contraseña de rol comprueba que cambia el verificador SCRAM, no el inicio de sesión.
3. **Roles ausentes:** los roles son globales del clúster y la sesión de tests los necesita, así que el mensaje de
   "faltan roles" se prueba llamando a `missing_roles` con un nombre inexistente, no ejecutando la migración sin
   roles. Cubre la lógica, no el camino completo por Alembic.
4. **Reguardar un lote ya existente** de 10.000 eventos tarda 4,0 s (más que el guardado inicial, 2,3 s) por la
   consulta que compara el contenido de los existentes. Está por debajo del umbral de 10 s; es un punto de
   mejora si fuese un caso frecuente.
5. **CI de GitHub no ejecutada:** el job `integration` (aprovisionamiento con la CLI real) y el `compose-smoke`
   modificado solo se han verificado por inspección de texto (`test_ci_workflow.py`) y reproduciendo sus pasos en
   local. El resultado real llegará tras el push.
6. El reloj de la base de datos del contenedor de Compose coincidía con el del host (la purga de la simulación
   calculó `cutoff` = ahora − 90 días).

## 8. Riesgos y decisiones pendientes

- Revisar la CI en cuanto se haga push; si falla el `compose-smoke`, corregirlo antes de dar el incremento por cerrado.
- `psycopg.sql` escribe la contraseña de rol como literal en el DDL: el servidor podría registrarla si
  `log_statement` está en `ddl` o `all`. Documentar en el runbook del incremento 7 que no debe activarse en
  producción.
- La paginación por desplazamiento puede desplazar páginas con inserciones concurrentes (decisión de la
  clarificación; documentada).
- Los umbrales de rendimiento son orientativos y se midieron en una sola máquina.

## 9. Commits

Pendientes de autorización explícita (T068 y T069).
