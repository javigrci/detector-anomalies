# Verificación del incremento 0

**Fecha:** 2026-11-13 · **Commit verificado:** `ce7322d` (más el cambio posterior de README) ·
**Entorno:** WSL2 (Ubuntu), Docker Desktop 29.3.0, Compose 5.1.0, uv 0.11.29, Python 3.12.3.

Todos los resultados son los observados en la ejecución; los tiempos son de una máquina de
desarrollo y no son garantías.

## Resultado global

| Comprobación | Resultado |
|---|---|
| Ruff (lint) | All checks passed |
| Ruff (formato) | 70 files already formatted |
| mypy estricto (`src` y `tests`) | 0 errores (21 + 19 archivos) |
| pytest sin integración | **85 passed**, 2 deselected |
| pytest integración (PostgreSQL 16 real) | **2 passed** |
| `alembic upgrade head` | salida 0, sin tablas de negocio |
| `docker compose up --build -d --wait` | API y base de datos *Healthy*; `/health` 200, `/ready` 200 |
| CI en GitHub (run 43423457154) | `quality`, `integration` y `compose-smoke`: **success** |
| Clon limpio siguiendo el README | todo verde en 24 s (con imágenes ya descargadas) |

## Escenarios de `quickstart.md`

| # | Escenario | Resultado |
|---|---|---|
| 1 | Calidad en local | OK. Fallos provocados (Ruff lint y formato, mypy, pytest, lock desactualizado) → salida 1 en los cinco; controles con el lock vigente → salida 0 |
| 2 | Arranque completo | OK. 33 s incluyendo construcción de la imagen. `/health` y `/ready` en 200 |
| 3 | Base de datos caída | OK. `/health` 200; `/ready` 503 con `not_ready` en ≈3,6 s; al volver la base de datos, 200 en 1 s sin reiniciar la API |
| 4 | Arranque sin base de datos | OK con `docker compose up -d --no-deps --build api`; `/health` 200 y `/ready` 503; al arrancar `db`, `/ready` 200 en 2 s |
| 5 | Trazabilidad | OK. Cabecera válida conservada; ausente, con espacios o de 70 caracteres → UUID nuevo; mismo id en cabecera, sobre de error y log; la query `?token=…` no aparece en los logs |
| 6 | Configuración inválida | OK. Sin `DATABASE_URL`: salida 2 y «DATABASE_URL: obligatoria», sin valores |
| 7 | Migraciones | OK. `alembic upgrade head` salida 0 (en local y dentro del contenedor) |
| 8 | CI | Los tres jobs pasan en GitHub. **No se provocó un fallo en la propia CI**; los fallos provocados se hicieron en local (escenario 1) |

Comprobaciones adicionales de T032: el proceso del contenedor corre como UID 10001 (no root);
`docker image inspect` no muestra variables sensibles; con `API_PORT=9000` el servicio y su
`HEALTHCHECK` funcionan; con el puerto 8000 ocupado Docker falla con un error claro y
`API_PORT=8010` lo resuelve.

## Requisitos funcionales

| FR | Evidencia |
|---|---|
| 000-01 | `uv sync --frozen` en clon limpio; `uv lock --check` falla con lock desactualizado |
| 000-02 | `tests/unit/test_package_structure.py` (8 paquetes) |
| 000-03 | `test_config.py`, `test_main_entrypoint.py`; escenario 6 |
| 000-04 | `.env.example`, `.gitignore`, `test_repo_hygiene.py`; `.env` nunca versionado |
| 000-05 | `test_logging.py`, `test_request_logging.py`; logs JSON en Compose |
| 000-06 | `test_request_id_middleware.py`; escenario 5 |
| 000-07 | `test_health.py`; escenarios 2–4 |
| 000-08 | `test_ready.py`, `test_ready_db.py`; escenarios 3–4 |
| 000-09 | `test_health.py`, `test_openapi_contract.py` |
| 000-10 | `test_errors.py`; 404, 405, 422, 500 con el mismo sobre |
| 000-11 | `compose.yaml`; escenario 2 |
| 000-12 | UID 10001, imagen sin variables sensibles, `test_repo_hygiene.py` |
| 000-13 | README + CI; escenario 1 |
| 000-14 | 85 tests unitarios + 2 de integración |
| 000-15 | marcador `integration` en `pyproject.toml` |
| 000-16 | `README.md`, `test_readme.py`, clon limpio |
| 000-17 | OpenAPI solo documenta `/health` y `/ready`; dependencias = SPEC §2 + `psycopg` (ADR 0002); sin lógica en `ingestion`, `features`, `ml`, `scoring`, `schemas` |
| 000-18 | `.github/workflows/ci.yml`, `test_ci_workflow.py`, run en verde |
| 000-19 | `alembic.ini`, `storage/migrations/`, `test_alembic.py` |

## Criterios de éxito

| SC | Evidencia |
|---|---|
| 001 | Clon limpio → verificado en 24 s con imágenes ya descargadas. **No se midió un arranque en frío** |
| 002 | `/health` y `/ready` en 200 al terminar `--wait` (arranque completo en 33 s) |
| 003 | 100 % de los tests y comprobaciones en verde; fallos provocados bloquean cada paso en local |
| 004 | Cabecera `X-Request-ID` en respuestas 200, 404, 422 y 500 (tests) y en cada log de petición |
| 005 | `/ready` refleja el fallo en ≈3,6 s (< 5 s) y se recupera en 1 s (< 30 s) |
| 006 | Escaneo del árbol y de los 4 commits: sin secretos; `.env` nunca versionado |
| 007 | Dos instalaciones desde el mismo lock (proyecto y clon limpio) idénticas: `uv sync --frozen` |

## Desviaciones y observaciones

1. **Margen de SC-005 corto:** `/ready` tarda ≈3,6 s con la base de datos parada aunque el
   timeout de conexión es 2 s (probablemente por la resolución DNS de `db` cuando el contenedor
   no existe). Cumple (< 5 s), pero con poco margen.
2. **Orden del plan:** el middleware de `request_id` se implementó en US4 (después de los
   contenedores), no en la fase de servicio; `tasks.md` es el orden vigente.
3. **Protección de rama no disponible:** GitHub responde 403 para este repositorio privado; la CI
   informa pero no puede bloquear fusiones. Documentado en el README.
4. **Aviso de dependencia:** `starlette.testclient` avisa de que el uso de `httpx` está en desuso
   y recomienda `httpx2`. `httpx` es la dependencia de SPEC §2; el aviso no afecta a los tests,
   pero conviene revisarlo antes del incremento 5.
5. **Mensajes en inglés:** el `message` del 404 es el de Starlette (`Not Found`); el resto de
   mensajes propios está en español. Cosmético, sin cambiar.
6. **Cobertura mínima de tests:** diferida, como se acordó en la clarificación; no se midió.
7. **Un test se ajustó durante la implementación:** `test_sensitive_data_is_never_logged` leía
   también los logs de `httpx` (cliente de pruebas); ahora solo evalúa los registros de la
   aplicación. La aplicación ya cumplía.
8. **Filtro de seguridad de la herramienta:** un comando de creación de archivos fue bloqueado
   por falso positivo (no contenía ningún borrado); los archivos se crearon sin incidencias.
