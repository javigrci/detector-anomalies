---

description: "Tareas del incremento 2 — Persistencia de eventos"
---

# Tasks: Persistencia de eventos

**Input**: Documentos de diseño en `/specs/002-persistence/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (`storage-api.md`, `operations.md`, `environment.md`), quickstart.md

**Tests**: OBLIGATORIOS (Constitución, Principio V). Cada historia y cada módulo compartido empiezan por sus tareas de test; se escriben y se confirma que FALLAN antes de implementar. Los resultados se registran tal como salen.

**Organization**: Tareas agrupadas por historia de usuario en el orden de entrega del plan: Cimientos → Migración → US1 → US2 → US3 → US4 → US5 → US6 → Cierre. Los módulos `events.py` y `__init__.py` crecen a lo largo de varias historias, así que esas tareas son secuenciales entre sí.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1…US6)
- Cada tarea cita requisitos (FR-002-xx) y rutas exactas

## Notas de ejecución

- **Aprobado por el usuario (2026-11-22):** la CLI mínima `python -m security_anomaly.storage`, los servicios de Compose bajo perfiles `setup` y `maintenance`, y las variables de entorno nuevas (research R10; AGENTS.md regla 3). Nada más fuera de la spec.
- Se trabaja en `main`; los commits y pushes (T068 y T069) requieren autorización explícita (Principio VII).
- **Sin dependencias nuevas**: SQLAlchemy 2 (Core), Alembic, `psycopg` 3, Pydantic v2 y biblioteca estándar. Si surge la necesidad de otra, parar y pedir aprobación (ADR).
- Las contraseñas y claves de los tests se **generan al vuelo** (`secrets.token_hex`); nunca valores fijos ni reales. Las tres contraseñas de rol son distintas entre sí.
- Los tests de integración usan una base de datos efímera por sesión (`CREATE DATABASE`) y fallan (no se saltan) si falta `DATABASE_URL`, como en el incremento 0.
- Los fixtures de fugas llevan **cadenas centinela** (`SENTINEL-USER-…`, `SENTINEL-PASSWORD-…`) para comprobar que no aparecen en errores, logs ni salidas.
- Datos ficticios: IPs de rangos de documentación (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`), usuarios `user001…`, hosts `srv-demo-NN`.
- Comandos de verificación por tarea: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`, y `uv run pytest -q -m "not integration"` o `-m integration` (PostgreSQL temporal de `docs/handoff.md` §8).

---

## Phase 1: Setup (infraestructura compartida)

**Purpose**: estructura de directorios y variables de entorno nuevas.

- [X] T001 Crear los directorios y `__init__.py`: `tests/unit/storage/__init__.py` y `tests/integration/storage/__init__.py`; comprobar que Ruff y mypy siguen en verde
- [X] T002 Ampliar `tests/unit/test_repo_hygiene.py` (test primero): `EXPECTED_VARS` incluye `MIGRATION_DATABASE_URL`, `MAINTENANCE_DATABASE_URL`, `ADMIN_DATABASE_URL`, `MIGRATOR_DB_PASSWORD`, `APP_DB_PASSWORD`, `MAINT_DB_PASSWORD`, `RETENTION_DAYS`, `QUERY_DEFAULT_LIMIT` y `QUERY_MAX_LIMIT` de `contracts/environment.md`; las tres contraseñas y las tres URL con credenciales deben contener el marcador `change-me`; confirmar que falla (FR-002-23)
- [X] T003 Añadir a `.env.example` las variables de T002 con marcadores `change-me-…` (contraseñas distintas entre sí, aptas para URL) y los valores por defecto 90, 100 y 1000; cambiar el comentario de `DATABASE_URL` para indicar que usa el rol `anomaly_app` (FR-002-22, FR-002-23; contracts/environment.md) (T002)

---

## Phase 2: Foundational (prerrequisitos bloqueantes)

**Purpose**: configuración, errores, modelos, tabla, roles, migración y fixtures de integración que necesitan todas las historias.

**⚠️ CRITICAL**: ninguna historia puede empezar hasta terminar esta fase.

### Configuración y errores

- [X] T004 [P] Test en `tests/unit/storage/test_config.py` (primero): `StoragePolicy` (defaults 90/100/1000; `retention_days ≥ 1`; `query_default_limit ≤ query_max_limit`); `MigrationSettings`, `MaintenanceSettings` y `AdminSettings` leen sus variables vía `load_model`; contraseñas distintas, ≥ 12 caracteres, sin `change-me` ni `@ : / ? # %`; vacío = ausente; los mensajes nombran la variable y nunca el valor (centinela); confirmar que falla (FR-002-15, FR-002-19, FR-002-22)
- [X] T005 [P] Test en `tests/unit/storage/test_errors.py` (primero): `StorageError` con `code ∈ {unavailable, permission_denied, integrity, unknown}` derivado del SQLSTATE (`08xxx`/conexión → `unavailable`, `42501` → `permission_denied`, `23xxx` → `integrity`, resto → `unknown`), mensaje fijo, sin credenciales, valores ni sentencia (centinelas), excepción original descartada (`from None`); confirmar que falla (FR-002-25)
- [X] T006 Implementar `src/security_anomaly/storage/config.py` (`StoragePolicy`, `MigrationSettings`, `MaintenanceSettings`, `AdminSettings`) con `SecretStr` y `load_model` del incremento 1, sin tocar `Settings`; T004 pasa (T004)
- [X] T007 [P] Implementar `src/security_anomaly/storage/errors.py` (`StorageError` y la función de traducción desde excepciones de SQLAlchemy/psycopg); T005 pasa (T005)

### Modelos y tabla

- [X] T008 [P] Test en `tests/unit/schemas/test_storage_models.py` (primero): `EventFilter` (fechas con zona horaria, `date_from < date_to`, catálogos, IP normalizada a forma comprimida incluidas equivalentes IPv6, `user_pseudonym` solo `usr_[0-9a-f]{32}` y rechaza un nombre real, `source` con su formato); `StoredEvent` (UTC); `EventPage`; `SaveSummary` (invariante `inserted + existing`); `PurgeResult`; todos inmutables; confirmar que falla (FR-002-01, FR-002-03, FR-002-13, FR-002-17)
- [X] T009 Implementar `src/security_anomaly/schemas/storage.py` (`EventFilter`, `StoredEvent`, `EventPage`, `SaveSummary`, `PurgeResult`) reutilizando enums de `schemas/event.py`; T008 pasa (T008)
- [X] T010 [P] Test en `tests/unit/storage/test_schema.py` (primero): la `Table` `events` tiene exactamente las columnas, nulabilidad y clave primaria `(source, event_id)` de `data-model.md`, no tiene `username`, `out_of_order` ni `position` (FR-002-02, FR-002-06), y declara los índices de `data-model.md` con los parciales de IP y usuario (FR-002-18); confirmar que falla
- [X] T011 Implementar `src/security_anomaly/storage/schema.py` (`MetaData` y `Table` `events` en SQLAlchemy Core); T010 pasa (T010)

### Roles y aprovisionamiento

- [X] T012 [P] Test en `tests/unit/storage/test_roles.py` (primero): nombres de rol como constantes (`anomaly_migrator`, `anomaly_app`, `anomaly_maint`); las sentencias de `provision_roles` escriben las contraseñas como literales con `psycopg.sql` (una contraseña con comilla simple no rompe ni inyecta) y no se registran en logs; confirmar que falla (FR-002-22, FR-002-24)
- [X] T013 Implementar `src/security_anomaly/storage/roles.py` (`RolePasswords`, constantes de rol, `provision_roles(admin_engine, passwords)` idempotente: crea o actualiza la contraseña, `CONNECT`, `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, `CREATE`/`USAGE` en `public` para el migrador, `USAGE` para los otros dos); T012 pasa (T012, T006)

### ADR y fixtures de integración

- [X] T014 [P] Escribir `docs/decisions/0003-rotacion-pseudonym-key.md` (español) con los cinco puntos de research R12: reingerir tras rotar no es idempotente; el nombre original no se guarda, así que no se puede reseudonimizar; procedimiento (detener ingesta → purgar o aceptar explícitamente el corte → rotar → reanudar); coste; evolución con columna de versión de clave (FR-002-27, US6)
- [X] T015 Crear `tests/integration/storage/conftest.py` con las fixtures de sesión. En los tests, `DATABASE_URL` es la conexión de **administrador de PostgreSQL** (el superusuario `postgres` de la CI y del handoff §8), solo para crear la base de datos efímera y aprovisionar roles; no es la URL del rol de aplicación. Fixtures: base de datos efímera (`CREATE DATABASE` con un nombre aleatorio), tres contraseñas aleatorias distintas, `provision_roles`, los motores `admin_engine`, `migrator_engine`, `app_engine` y `maint_engine`, una fixture `migrated` que aplica Alembic, una que vacía `events` entre tests (con el migrador) y un generador de `NormalizedEvent` ficticios y deterministas; la limpieza elimina la base de datos al terminar. Hasta T019 esta tarea se verifica solo con la creación de la base de datos y los roles; la fixture `migrated` se valida con T017–T019 (FR-002-28; research R13) (T013, T011; `migrated` depende de T018 y T019)

### Migración

- [X] T016 [P] Test unitario en `tests/unit/storage/test_migration_catalog.py` (primero): los valores de las `CHECK` de la migración `0001` (`event_type`, `action`, `outcome`, formato de `source` y de `user_pseudonym`) coinciden con los enums y patrones de `schemas/event.py`; falla si divergen (riesgo del plan); confirmar que falla (FR-002-01)
- [X] T017 Reescribir `tests/integration/test_alembic.py` (primero; antes comprobaba que no había tablas de negocio): con los roles aprovisionados, `alembic upgrade head` con `MIGRATION_DATABASE_URL` crea `events` con sus índices y `CHECK`; repetirlo no cambia nada ni falla; sin los roles falla con un mensaje que pide aprovisionar (sin valores); `downgrade` se niega con filas salvo `-x destructive=yes` y con la tabla vacía funciona; confirmar que falla (FR-002-05, FR-002-22; Principio VII) (T015)
- [X] T018 Escribir `src/security_anomaly/storage/migrations/versions/0001_create_events.py` a mano: tabla `events`, clave primaria, `CHECK` de catálogo, formato de `source`, `event_id` 1–256, `host` ≤ 256 y `usr_…`, los seis índices de `data-model.md`, `GRANT SELECT, INSERT` a `anomaly_app` y `SELECT, DELETE` a `anomaly_maint`, comprobación previa de que existen los roles; `downgrade()` protegido por `-x destructive=yes`; T016 y T017 pasan (T016, T017)
- [X] T019 Actualizar `src/security_anomaly/storage/migrations/env.py`: leer `MIGRATION_DATABASE_URL` mediante `MigrationSettings`, `target_metadata` con la `Table` de `schema.py` y soporte de `-x destructive=yes`; no usar `DATABASE_URL` (FR-002-22) (T006, T011)
- [X] T020 Actualizar `.github/workflows/ci.yml` (job `integration`): variables de rol generadas al vuelo con `openssl rand -hex 12` (distintas), `provision-roles` antes de `alembic upgrade head` con `MIGRATION_DATABASE_URL`; ajustar `tests/unit/test_ci_workflow.py` si comprueba esos pasos (FR-002-28) (T019)

**Checkpoint**: configuración, modelos, tabla, roles, migración y fixtures listos; las historias pueden empezar.

---

## Phase 3: User Story 1 - Guardar un lote ingerido sin duplicar nada (Priority: P1) 🎯 MVP

**Goal**: guardado idempotente, atómico y concurrente de eventos normalizados con resumen de insertados, existentes y existentes con contenido distinto.

**Independent Test**: guardar un lote, repetirlo y guardar otro solapado; comparar recuentos y contenido almacenado.

### Tests for User Story 1 (MANDATORY) ⚠️

> Escribirlos primero y confirmar que FALLAN antes de implementar.

- [X] T021 [P] [US1] Test unitario en `tests/unit/storage/test_save_logic.py`: conversión de `NormalizedEvent` a fila (sin `username`, `out_of_order` ni `position`, sin hora de ingesta propia); colapso de repetidos dentro de la entrada (gana el primero y cuentan como `existing`); orden por `(source, event_id)`; troceado en bloques de 1.000; comparación de contenido de siete campos; invariante `inserted + existing == entrada`; un evento sin usuario da seudónimo nulo (FR-002-02, FR-002-06, FR-002-07, FR-002-09)
- [X] T022 [P] [US1] Test de integración en `tests/integration/storage/test_save_idempotent.py`: base vacía → N insertados; repetir → 0 insertados y N existentes sin filas nuevas; dos lotes solapados suman bien; mismo `(source, event_id)` con contenido distinto conserva el original y cuenta en `existing_with_different_content`; `ingested_at` no cambia al reguardar; lote de 10.000 en una transacción; los eventos insertados llevan el `batch_id` del resumen y dos guardados distintos generan identificadores distintos; un guardado en el que todos los eventos ya existían no deja ninguna fila nueva ni rastro del `batch_id` (FR-002-07…09, FR-002-11, FR-002-19; US1.1–1.4; US4.8)
- [X] T023 [P] [US1] Test de integración en `tests/integration/storage/test_save_concurrent.py`: varios hilos guardando eventos solapados con claves en distinto orden terminan sin error, sin interbloqueo y con cada evento una sola vez (FR-002-08; SC-002; US1.6)
- [X] T024 [P] [US1] Test de integración en `tests/integration/storage/test_save_atomic.py`: un fallo forzado a mitad de un lote (por ejemplo, una fila que viola una `CHECK`) deja 0 eventos de ese lote; el `StorageError` no contiene valores ni credenciales (centinelas); con la base de datos caída da `code=unavailable` (FR-002-10, FR-002-25; US1.5)
- [X] T025 [P] [US1] Test de integración en `tests/integration/storage/test_no_username_stored.py`: se guardan eventos de la ingesta real con usuarios centinela y ninguna columna de ninguna tabla, ni el volcado de la base de datos, contiene el nombre original; solo `usr_…`; además, un lote de la ingesta que mezcla registros válidos y rechazados guarda únicamente los válidos (FR-002-02, FR-002-12; SC-006; US1.7)
- [X] T026 [P] [US1] Test en `tests/unit/storage/test_save_logging.py`: `events_saved` registra solo recuentos, duración e identificador de lote (con `caplog`, sin centinelas de evento) (FR-002-26)

### Implementation for User Story 1

- [X] T027 [US1] Implementar `save_events` en `src/security_anomaly/storage/events.py`: una transacción (`engine.begin()`), filas ordenadas por clave, bloques de 1.000 con `INSERT … ON CONFLICT (source, event_id) DO NOTHING RETURNING`, lectura de las existentes por claves y comparación de contenido, `batch_id` generado si falta, errores traducidos con `StorageError`; T021–T025 pasan (T021–T025, T007, T009, T011, T018)
- [X] T028 [US1] Añadir el log `events_saved` (recuentos, duración, `batch_id`) en `save_events`; T026 pasa (T026, T027)
- [X] T029 [US1] Exportar la API en `src/security_anomaly/storage/__init__.py` (`save_events`, `StorageError`, modelos) y añadir a `tests/unit/storage/test_public_api_contract.py` la comprobación de firma de `contracts/storage-api.md` (T027)

**Checkpoint**: US1 funcional y comprobable de forma independiente.

---

## Phase 4: User Story 2 - Consultar eventos con filtros y paginación estable (Priority: P1)

**Goal**: filtros combinables, orden total, paginación por tamaño y desplazamiento con total.

**Independent Test**: almacenar un conjunto conocido, combinar filtros y recorrer todas las páginas.

### Tests for User Story 2 (MANDATORY) ⚠️

- [X] T030 [P] [US2] Test unitario en `tests/unit/storage/test_query_build.py`: el SQL compilado nunca contiene los valores de los filtros (todo es parámetro enlazado, con centinelas como `'; DROP TABLE events; --`); orden `timestamp, source, event_id`; conjunción de los filtros presentes; el filtro de IP compara como `inet`; `limit` por defecto 100, entre 1 y el máximo; `offset ≥ 0`; los inválidos lanzan antes de abrir una conexión (motor simulado que falla si se usa) (FR-002-13…15, FR-002-17, FR-002-24; US2.5)
- [X] T031 [P] [US2] Test de integración en `tests/integration/storage/test_query_filters.py`: cada filtro por separado y en conjunción; rango `[desde, hasta)`; IPv6 abreviada y completa equivalentes; nulos (sin usuario, sin IP, sin host) no rompen filtros ni orden; filtro por seudónimo; sin resultados → página vacía con total 0 (FR-002-13, FR-002-17; US2.1, 2.2, 2.6, 2.7)
- [X] T032 [P] [US2] Test de integración en `tests/integration/storage/test_query_pagination.py`: 5.000 eventos con páginas de 100 devuelven cada uno exactamente una vez y en el mismo orden en ejecuciones repetidas; la respuesta trae total, `limit` y `offset`; los timestamps salen en UTC (FR-002-03, FR-002-14; SC-003; US2.3, 2.4)
- [X] T033 [P] [US2] Test de integración en `tests/integration/storage/test_query_injection.py`: filtros con caracteres hostiles (comillas, `%`, `;`, unicode) se rechazan por formato o se tratan como datos sin alterar la tabla; un nombre de usuario real como filtro se rechaza (FR-002-17, FR-002-24)
- [X] T034 [P] [US2] Test en `tests/unit/storage/test_query_logging.py`: `events_queried` registra solo qué campos de filtro se usaron, recuentos y duración, nunca sus valores (FR-002-26)

### Implementation for User Story 2

- [X] T035 [US2] Implementar `query_events` en `src/security_anomaly/storage/events.py`: construcción con `select().where()`, `count(*)` bajo los mismos filtros, orden total, validación previa, `StoragePolicy`, mapeo a `StoredEvent` en UTC y log `events_queried`; T030–T034 pasan (T030–T034, T027)
- [X] T036 [US2] Documentar en el docstring de `query_events` que las inserciones concurrentes pueden desplazar páginas y que `read_range` ofrece exactitud (FR-002-14), y exportar `query_events` y `EventFilter` en `src/security_anomaly/storage/__init__.py` (T035)

**Checkpoint**: US1 y US2 funcionan de forma independiente.

---

## Phase 5: User Story 3 - Leer eventos por rango temporal sin fuga de futuro (Priority: P2)

**Goal**: lectura `[desde, hasta)` en orden cronológico por bloques, con paginación por clave.

**Independent Test**: eventos repartidos en el tiempo, ventanas distintas, orden y límites.

### Tests for User Story 3 (MANDATORY) ⚠️

- [X] T037 [P] [US3] Test unitario en `tests/unit/storage/test_read_range_validation.py`: `start` y `end` sin zona horaria, `start >= end` y `chunk_size < 1` se rechazan antes de consultar; la consulta compilada usa `>= :start AND < :end` y la comparación de tupla `(timestamp, source, event_id) > (…)` con parámetros enlazados (FR-002-16, FR-002-24)
- [X] T038 [P] [US3] Test de integración en `tests/integration/storage/test_read_range.py`: orden cronológico ascendente con desempate determinista; ningún evento con `timestamp >= end` ni `< start`, incluida una ventana que termina justo en el `timestamp` de un evento; eventos guardados fuera de orden o en lotes distintos salen por su `timestamp`; mismo timestamp, mismo orden siempre (FR-002-16; Principio III; NFR-04; US3.1, 3.2, 3.4, 3.5)
- [X] T039 [P] [US3] Test de integración en `tests/integration/storage/test_read_range_chunks.py`: un rango grande con `chunk_size` pequeño devuelve todo sin duplicados ni saltos; ningún bloque supera `chunk_size` (memoria acotada); se puede insertar entre bloques sin duplicar ni perder los ya fijados en el rango (FR-002-16; US3.3)
- [X] T040 [P] [US3] Test de rendimiento en `tests/integration/storage/test_perf_query.py` (marcador `integration`): 100.000 eventos y lectura de un día en menos de 1 s (el umbral del test es el de SC-004; solo se ajusta con una justificación registrada) y `EXPLAIN` que usa el índice de `timestamp`; se registran el tiempo real, el volumen, el hardware y las condiciones (Constitución VI) (SC-004; FR-002-18)

### Implementation for User Story 3

- [X] T041 [US3] Implementar `read_range` en `src/security_anomaly/storage/events.py`: generador de bloques con paginación por clave, límite superior exclusivo en la propia consulta, cada bloque en su consulta corta; T037–T040 pasan (T037–T040, T035)
- [X] T042 [US3] Exportar `read_range` en `src/security_anomaly/storage/__init__.py` y ampliar `test_public_api_contract.py` (T041)

**Checkpoint**: US1, US2 y US3 funcionan.

---

## Phase 6: User Story 4 - Retener datos solo el tiempo necesario (Priority: P2)

**Goal**: purga explícita por bloques, con simulación y CLI, medida desde la ingesta.

**Independent Test**: eventos con antigüedades conocidas, simular y ejecutar la purga.

### Tests for User Story 4 (MANDATORY) ⚠️

- [X] T043 [P] [US4] Test unitario en `tests/unit/storage/test_retention_logic.py`: cálculo de `cutoff = now − retention_days`; `retention_days < 1` → `ValueError` sin abrir conexión (motor simulado); por defecto `StoragePolicy.retention_days` (90) o `RETENTION_DAYS`; troceado de 5.000 (FR-002-19, FR-002-21; US4.5, 4.6)
- [X] T044 [P] [US4] Test unitario en `tests/unit/storage/test_cli.py`: `provision-roles` y `purge [--days N] [--dry-run]` con `argparse`; salida de **una línea JSON** con `retention_days`, `cutoff`, `dry_run`, `affected`; códigos 0, 1 (solo el `code` del `StorageError`) y 2 (configuración o argumentos inválidos, nombrando la variable y no su valor); `--days` sustituye a `RETENTION_DAYS` y debe ser ≥ 1; sin URL de mantenimiento no hace nada; nunca imprime credenciales ni valores (centinelas) (FR-002-20, FR-002-26; contracts/operations.md)
- [X] T045 [P] [US4] Test de integración en `tests/integration/storage/test_purge.py` (envejeciendo `ingested_at` con el migrador): borra solo los más antiguos que el periodo y el resumen cuenta cuántos; la simulación informa sin borrar; sin purga no se borra nada con el tiempo; repetir borra 0; periodo cero o negativo se rechaza sin borrar; eventos con `timestamp` antiguo recién ingeridos no se purgan; reguardar un evento existente no reinicia su retención; un periodo mayor que toda la antigüedad no borra nada (FR-002-19…21; SC-005; US4.1–4.8)
- [X] T046 [P] [US4] Test de integración en `tests/integration/storage/test_purge_blocks.py`: más de 5.000 candidatos se borran en varios bloques, una transacción por bloque, y mientras corre otra conexión puede insertar y leer sin quedarse bloqueada de forma prolongada (FR-002-21)
- [X] T047 [P] [US4] Test de integración en `tests/integration/storage/test_purge_role.py`: la purga con las credenciales del rol de aplicación se deniega (`StorageError` `permission_denied`) y no borra nada (FR-002-20, FR-002-22)
- [X] T048 [P] [US4] Test en `tests/unit/storage/test_purge_logging.py`: `events_purged` registra solo recuentos, `cutoff` y duración (FR-002-26)

### Implementation for User Story 4

- [X] T049 [US4] Implementar `purge_events` en `src/security_anomaly/storage/retention.py`: validación previa, `cutoff` con el reloj de la base de datos si falta `now`, simulación con `count(*)`, bucle `DELETE … WHERE (source, event_id) IN (SELECT … LIMIT 5000)` con una transacción por bloque, log `events_purged`; T043, T045–T048 pasan (T043, T045–T048, T007, T018)
- [X] T050 [US4] Implementar la CLI en `src/security_anomaly/storage/__main__.py` (solo `argparse`): `provision-roles` con `AdminSettings` y `purge` con `MaintenanceSettings` y `StoragePolicy`; T044 pasa (T044, T049, T013)
- [X] T051 [US4] Exportar `purge_events` y `provision_roles` en `src/security_anomaly/storage/__init__.py` y ampliar `test_public_api_contract.py` (T049)

**Checkpoint**: US1 a US4 funcionan.

---

## Phase 7: User Story 5 - Separar quién migra, quién usa y quién purga (Priority: P2)

**Goal**: tres roles con mínimos privilegios y entorno Compose que los aprovisiona desde cero.

**Independent Test**: conectar con cada rol e intentar las operaciones permitidas y prohibidas.

### Tests for User Story 5 (MANDATORY) ⚠️

- [X] T052 [P] [US5] Test de integración en `tests/integration/storage/test_privileges.py`: tabla de `contracts/operations.md` completa. Rol de aplicación: `INSERT` y `SELECT` sí; `DELETE`, `TRUNCATE`, `UPDATE`, `CREATE TABLE`, `ALTER TABLE` y `DROP TABLE` denegados. Rol de mantenimiento: `DELETE` y `SELECT` sí; `INSERT`, `UPDATE`, `TRUNCATE` y DDL denegados. Migrador: todo. Cada intento denegado se comprueba contra el estado real de la base de datos (SC-007; US5.1–5.3)
- [X] T053 [P] [US5] Test de integración en `tests/integration/storage/test_provision_roles.py`: `provision_roles` es idempotente, un segundo uso con otra contraseña la actualiza (se puede iniciar sesión con la nueva y no con la vieja), `PUBLIC` no tiene `CREATE` en `public`, y los errores no contienen contraseñas (centinelas) (FR-002-22; US5.4, 5.5)
- [X] T054 [P] [US5] Test unitario en `tests/unit/test_compose_config.py` (primero): `compose.yaml` define `db-setup` con perfil `setup` y `db-maintenance` con perfil `maintenance` (no arrancan con `up`); `db` sin `ports`; la API usa `anomaly_app` y no recibe `MAINTENANCE_DATABASE_URL`, `ADMIN_DATABASE_URL` ni `MIGRATION_DATABASE_URL`; no hay contraseñas en claro en `compose.yaml` ni en `Dockerfile` (FR-002-23, FR-002-22); confirmar que falla

### Implementation for User Story 5

- [X] T055 [US5] Actualizar `compose.yaml`: añadir `db-setup` (perfil `setup`: `provision-roles` y `alembic upgrade head`, con las credenciales del administrador y del migrador) y `db-maintenance` (perfil `maintenance`: `purge --dry-run` por defecto, con `MAINTENANCE_DATABASE_URL`); cambiar `DATABASE_URL` de la API al rol `anomaly_app` con `APP_DB_PASSWORD` y mantener la base de datos sin publicar; usar `${VAR:?mensaje}` para las contraseñas; T054 pasa (T054, T050, T019)
- [X] T056 [US5] Actualizar el job `compose-smoke` de `.github/workflows/ci.yml`: sustituir las tres contraseñas de rol por valores aleatorios distintos, ejecutar `docker compose --profile setup run --rm db-setup` antes de comprobar `/ready` y una simulación `--profile maintenance run --rm db-maintenance purge --dry-run`; ajustar `tests/unit/test_ci_workflow.py` (US5.6; FR-002-28) (T055)
- [X] T057 [US5] Verificar en local el escenario 8 de `quickstart.md`: `up --wait` → `/health` 200 y `/ready` 503; `db-setup` → `/ready` 200; `db-maintenance` informa la simulación; la base de datos sigue sin publicarse; registrar el resultado tal como sale en `verification.md` (T055)

**Checkpoint**: US1 a US5 funcionan.

---

## Phase 8: User Story 6 - Decidir qué pasa al rotar la clave de seudonimización (Priority: P3)

**Goal**: ADR 0003 y pruebas del comportamiento observable que describe.

**Independent Test**: revisar el ADR y ejecutar los tests que reflejan su política.

### Tests for User Story 6 (MANDATORY) ⚠️

- [X] T058 [P] [US6] Test de integración en `tests/integration/storage/test_key_rotation.py`: el mismo `auth.log` ingerido con la clave A y con la clave B (generadas al vuelo) inserta dos veces (identificadores y seudónimos cambian, no es idempotente); tras purgar antes de rotar solo quedan los eventos con la clave nueva; ninguna columna guarda versión ni identificador de clave (FR-002-27; US6.1–6.4)
- [X] T059 [P] [US6] Test unitario en `tests/unit/test_adr_rotation.py`: `docs/decisions/0003-rotacion-pseudonym-key.md` existe y menciona los tres efectos (seudónimos, `event_id` del adaptador, idempotencia), la imposibilidad de reseudonimizar, el procedimiento de purgar antes de rotar y el coste (SC-008; US6.1, 6.2)

### Implementation for User Story 6

- [X] T060 [US6] Si T058 o T059 revelan una discrepancia con el ADR, corregir el ADR (T014) o el código para que coincidan; no se añaden columnas de versión de clave (FR-002-27) (T058, T059, T014)

**Checkpoint**: las seis historias funcionan.

---

## Phase 9: Polish y cierre

**Purpose**: rendimiento, documentación, escaneo de fugas, evidencia y revisión.

- [X] T061 [P] Test de rendimiento en `tests/integration/storage/test_perf_save.py`: guardar 10.000 eventos en menos de 10 s (el umbral del test es el de SC-001; solo se ajusta con una justificación registrada); se registran el tiempo real, el volumen, el hardware y las condiciones (Constitución VI) (SC-001; FR-002-07)
- [X] T062 [P] Test transversal en `tests/integration/storage/test_no_leaks.py`: con usuarios, contraseñas y claves centinela, recorrer guardado, consulta, rango, purga, CLI y errores, y comprobar que ningún nombre de usuario, contraseña ni URL aparece en datos almacenados, resultados, excepciones, logs ni salida de la CLI (SC-006; FR-002-25, FR-002-26)
- [X] T063 [P] Documentar en `README.md`: la persistencia, el orden `up` → `db-setup` → `db-maintenance`, que `/ready` da 503 hasta `db-setup`, la CLI, los tres roles, la limitación de la paginación por desplazamiento y la advertencia sobre datos sintéticos; actualizar `docs/data-contract.md` con los campos persistidos y los no persistidos (FR-002-06)
- [X] T064 [P] Actualizar `docs/handoff.md` (estado del incremento 2, aprobaciones, pendientes y número de tests) y `docs/roadmap.md` si procede
- [X] T065 Ejecutar la calidad completa: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`, `uv run pytest -q -m "not integration"` y `uv run pytest -q -m integration` contra PostgreSQL temporal; registrar los resultados reales sin editarlos; si algo falla, el incremento no está cerrado (AGENTS.md regla 6 y 8)
- [X] T066 Ejecutar el `quickstart.md` completo (escenarios 1 a 10) y escribir `specs/002-persistence/verification.md` con resultados reales, tiempos medidos (SC-001, SC-004) junto con hardware, volumen y condiciones, matriz FR/SC → test, riesgos y decisiones pendientes; marcar `[X]` solo lo comprobado (T065)
- [X] T067 Confirmar que no hay dependencias nuevas (`git diff` de `pyproject.toml` y `uv.lock` vacío), ni endpoints, ni tablas de predicciones o modelos, ni secretos en el diff (FR-002-29; AGENTS.md regla 3) (T065)
- [X] T068 **Requiere autorización explícita:** commit en `main` con el mensaje de cierre en español y la línea `Co-Authored-By` fijada por el entorno (T066, T067)
- [X] T069 **Requiere autorización explícita:** `git push` y comprobar que los cuatro jobs de la CI quedan en verde, anotando el identificador del run en `verification.md` (T068)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sin dependencias.
- **Foundational (Fase 2)**: depende de Setup; **bloquea** todas las historias.
- **Historias (Fases 3 a 8)**: dependen de Foundational. Orden de entrega: US1 → US2 → US3 → US4 → US5 → US6.
- **Cierre (Fase 9)**: depende de las historias.

### Dependencias entre historias

- **US1**: sin dependencias de otras historias (necesita `save_events` para poblar los datos de las demás).
- **US2, US3**: sus tests usan `save_events` de US1 como ayuda de carga, pero se pueden verificar con inserciones directas con el migrador; comparten `events.py`, así que sus tareas de implementación son secuenciales.
- **US4**: independiente; usa el rol de mantenimiento ya aprovisionado en Foundational.
- **US5**: la matriz de privilegios depende de la migración (T018); la parte de Compose depende de la CLI (T050).
- **US6**: depende de US1 (guardado) y US4 (purga).

### Dentro de cada historia

- Tests primero y confirmados en rojo; luego modelos, lógica, API pública y logs.
- Después de cada tarea: Ruff, mypy y los tests afectados.

### Parallel Opportunities

- T004, T005, T008, T010, T012, T014 y T016 (archivos distintos).
- Todos los tests de una historia marcados [P].
- US4 (T043–T048) y US6 (T058, T059) pueden prepararse en paralelo con US2 y US3 si hay capacidad, salvo `events.py`.
- T061 a T064 en el cierre.

## Parallel Example: User Story 1

```bash
# Tests de US1 juntos:
Task: "Test unitario en tests/unit/storage/test_save_logic.py"
Task: "Test de integración en tests/integration/storage/test_save_idempotent.py"
Task: "Test de integración en tests/integration/storage/test_save_concurrent.py"
Task: "Test de integración en tests/integration/storage/test_save_atomic.py"
Task: "Test de integración en tests/integration/storage/test_no_username_stored.py"
```

## Implementation Strategy

### MVP primero (US1)

1. Fase 1 y Fase 2 (cimientos y migración).
2. Fase 3 (US1): guardado idempotente y atómico.
3. **PARAR y validar** con el escenario 3 de `quickstart.md`.

### Entrega incremental

1. Cimientos → US1 → US2 → US3 (lo que necesita el incremento 3).
2. US4 y US5 (retención, privilegios y Compose) antes de usar datos reales.
3. US6 (rotación de clave) y cierre con `verification.md`.

## Cobertura de requisitos

| Requisito | Tareas |
|---|---|
| FR-002-01…06 | T008–T011, T016–T018, T021, T025 |
| FR-002-07…12 | T021–T029 |
| FR-002-13…17 | T030–T036, T037–T042 |
| FR-002-18 | T010, T018, T040 |
| FR-002-19…21 | T043–T051 |
| FR-002-22…23 | T002–T003, T012–T013, T052–T057 |
| FR-002-24…26 | T005, T007, T026, T030, T034, T048, T062 |
| FR-002-27 | T014, T058–T060 |
| FR-002-28…29 | T015, T020, T056, T067 |
| SC-001…008 | T061, T022/T023, T032, T040, T045, T062, T052, T018/T059 |

## Notes

- [P] = archivos distintos y sin dependencias pendientes.
- La etiqueta [Story] vincula cada tarea con su historia.
- Verificar que los tests fallan antes de implementar; si un test pasa sin código nuevo, hacer una prueba de mutación (acuerdo del handoff §7).
- Parar en cada checkpoint para validar la historia.
- Evitar: tareas vagas, conflictos en el mismo archivo y dependencias entre historias que rompan su independencia.
