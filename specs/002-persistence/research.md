# Research: Persistencia de eventos

Todas las decisiones respetan SPEC §2, §7 y §9 y la constitución. No quedan `NEEDS CLARIFICATION`.
**No se añade ninguna dependencia nueva**: SQLAlchemy 2, Alembic y `psycopg` ya están aprobados y
todo lo demás es biblioteca estándar.

## R1. Esquema de la tabla `events`

- **Decisión:** clave primaria compuesta natural `(source, event_id)`, sin clave sustituta.

| Columna | Tipo | Regla |
|---|---|---|
| `source` | `TEXT NOT NULL` | `CHECK (source ~ '^[a-z0-9][a-z0-9-]{0,63}$')` |
| `event_id` | `TEXT NOT NULL` | `CHECK (char_length(event_id) BETWEEN 1 AND 256)` |
| `timestamp` | `TIMESTAMPTZ NOT NULL` | siempre UTC al leer |
| `event_type` | `TEXT NOT NULL` | `CHECK` con el catálogo v1 |
| `action` | `TEXT NOT NULL` | `CHECK` con el catálogo v1 |
| `outcome` | `TEXT NOT NULL` | `CHECK (outcome IN ('success','failure','unknown'))` |
| `user_pseudonym` | `TEXT NULL` | `CHECK (user_pseudonym ~ '^usr_[0-9a-f]{32}$')` |
| `source_ip` | `INET NULL` | compara por valor: `2001:db8::1` y su forma completa son la misma |
| `host` | `TEXT NULL` | `CHECK (char_length(host) <= 256)` |
| `ingested_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | reloj de la base de datos; todas las filas de un lote lo comparten |
| `batch_id` | `UUID NOT NULL` | identificador del guardado |

- **Racional:** la clave natural da la unicidad en el propio almacenamiento (FR-002-04) y es el
  objetivo del `ON CONFLICT`; una clave sustituta añadiría una columna y un índice sin aportar nada.
  Las `CHECK` impiden que un cliente con acceso directo guarde datos que la ingesta habría
  rechazado, y que se guarde un nombre de usuario sin seudonimizar (formato `usr_…` obligatorio).
  Se copian en la migración como literales (una migración es una fotografía inmutable); cambiar el
  catálogo exige otra migración, igual que subir `catalog_version`.
- **No se persisten** `out_of_order` ni `position` (relativos a su lote, FR-002-06).
- **Alternativas:** tipos `ENUM` nativos (difíciles de modificar), `TEXT` sin `CHECK` (menos
  protección), clave sustituta `BIGINT` (más columnas, mismo resultado).

## R2. Índices

| Índice | Sirve a |
|---|---|
| PK `(source, event_id)` | unicidad y `ON CONFLICT` |
| `(timestamp, source, event_id)` | orden total determinista, rango temporal y paginación por clave |
| `(source, timestamp)` | filtro por fuente más rango |
| `(source_ip, timestamp)` parcial `WHERE source_ip IS NOT NULL` | filtro por IP más rango |
| `(user_pseudonym, timestamp)` parcial `WHERE user_pseudonym IS NOT NULL` | filtro por seudónimo más rango |
| `(ingested_at)` | purga por retención |

- **Decisión:** no se indexan `event_type`, `action` ni `outcome` por separado: tienen 2 a 4 valores y
  el planificador no los usa; se filtran sobre el índice de `timestamp`.
- **Racional:** cada índice secundario encarece el guardado; estos seis cubren las consultas de la
  spec. Se verificará con `EXPLAIN` en el quickstart que las consultas principales usan índice
  (SC-004).

## R3. Guardado idempotente y atómico

- **Decisión:** una sola transacción por lote (`engine.begin()`), con filas ordenadas por
  `(source, event_id)` e insertadas en bloques de 1.000 con
  `INSERT … ON CONFLICT (source, event_id) DO NOTHING RETURNING source, event_id`.
  - `RETURNING` da exactamente las filas insertadas; el resto ya existían.
  - Para las existentes se leen sus columnas con una consulta por claves y se comparan con las
    entrantes (`timestamp`, `event_type`, `action`, `outcome`, `user_pseudonym`, `source_ip`,
    `host`) para contar cuántas tenían contenido distinto (FR-002-07, FR-002-09).
  - `ON CONFLICT DO NOTHING` no modifica nada: `ingested_at` y el contenido originales se conservan
    (escenario 8 de la historia 4).
- **Concurrencia:** dos guardados que insertan la misma clave se serializan en el índice único: el
  segundo espera al primero y, al confirmarse, no inserta (FR-002-08). Ordenar por clave da un
  orden de bloqueo consistente entre transacciones y evita interbloqueos.
- **Atomicidad:** si algo falla, `ROLLBACK` del lote completo (FR-002-10).
- **Racional:** es el patrón estándar de PostgreSQL para idempotencia; bloques de 1.000 filas con 11
  parámetros quedan muy por debajo del límite de parámetros del protocolo.
- **Alternativas:** comprobar existencia antes y luego insertar (condición de carrera),
  `ON CONFLICT DO UPDATE` (sobrescribiría el original, contra FR-002-09), `COPY` (más rápido pero no
  admite `ON CONFLICT`).

## R4. Consulta con filtros y paginación

- **Decisión:** SQLAlchemy **Core** (sin ORM) con una `Table` declarada; las sentencias se construyen
  con `select().where()`, así que todo valor es un parámetro enlazado (FR-002-24).
- **Filtros** (`EventFilter`, modelo Pydantic validado antes de tocar la base de datos):
  `date_from`/`date_to` (con zona horaria, intervalo semiabierto `[from, to)` y `from < to`),
  `source` (formato de `source`), `event_type`/`action`/`outcome` (solo valores del catálogo),
  `source_ip` (IP válida; se compara como `inet`) y `user_pseudonym` (solo el formato `usr_…`, de
  modo que **nunca se acepta un nombre real**). Conjunción de todos los presentes.
- **Orden:** `ORDER BY timestamp, source, event_id` ascendente; orden total porque el último
  componente es la clave primaria.
- **Paginación:** `limit` y `offset`, `total` con un `count(*)` bajo los mismos filtros. Valores por
  defecto 100 y máximo 1.000 (configurable). Como decidió la clarificación, las inserciones
  concurrentes pueden desplazar páginas y queda documentado.
- **Alternativas:** paginación por cursor (descartada en la clarificación), ORM (más capas sin
  necesidad).

## R5. Lectura por rango temporal para el incremento 3

- **Decisión:** `read_range(start, end, chunk_size)` devuelve bloques por **paginación por clave**:
  `WHERE timestamp >= :start AND timestamp < :end AND (timestamp, source, event_id) > (:t, :s, :e)
  ORDER BY timestamp, source, event_id LIMIT :n`, repitiendo con el último elemento de cada bloque.
  Cada bloque es su propia consulta corta; la memoria queda acotada por `chunk_size` (5.000 por
  defecto).
- **Sin fuga de futuro:** el límite superior es exclusivo y se aplica en la propia consulta
  (FR-002-16); un test comprueba que nunca sale un evento con `timestamp >= end`.
- **Racional:** exacta sin duplicados ni saltos para el rango fijo y no depende de `offset` (que
  degrada con rangos grandes). Usa el índice `(timestamp, source, event_id)`.
- **Alternativas:** un cursor del servidor (mantiene una transacción abierta), `offset` (lento y
  desplazable).

## R6. Retención y purga

- **Decisión:** el periodo se mide desde `ingested_at` (clarificación). `purge_events(retention_days,
  dry_run, now)` calcula `cutoff = now − retention_days` (con `now` opcional, por defecto el reloj
  de la base de datos) y:
  - **Simulación:** `SELECT count(*) WHERE ingested_at < cutoff` y no borra.
  - **Borrado:** bucle de `DELETE … WHERE (source, event_id) IN (SELECT … WHERE ingested_at < cutoff
    LIMIT 5000)`, **una transacción por bloque**, hasta que un bloque borra menos de 5.000. Los
    bloqueos son cortos y no bloquea la base de datos de forma prolongada (FR-002-21).
- `retention_days` debe ser ≥ 1; si no, error antes de tocar la base de datos. Valor por defecto 90
  (`RETENTION_DAYS`). Repetir la purga borra 0 (FR-002-20).
- **`now` es solo un parámetro de cálculo:** permite probar sin esperar 90 días; no concede ningún
  privilegio adicional.
- **Alternativas:** `TRUNCATE` (no permite filtrar y es más privilegiado), una sola sentencia
  `DELETE` (bloqueo largo con millones de filas), particionado por fecha (complejidad innecesaria
  ahora).

## R7. Roles y privilegios

- **Decisión:** tres roles con nombres fijos como constantes del código:

| Rol | Privilegios |
|---|---|
| `anomaly_migrator` | propietario del esquema de la aplicación: `CREATE` en `public`; ejecuta las migraciones |
| `anomaly_app` | `SELECT`, `INSERT` sobre `events` |
| `anomaly_maint` | `SELECT`, `DELETE` sobre `events` (el `SELECT` es necesario para evaluar el `WHERE` y contar) |

  Ningún rol de aplicación o mantenimiento tiene `CREATE`, `ALTER`, `DROP`, `TRUNCATE` ni
  `UPDATE`. El esquema `public` queda sin `CREATE` para `PUBLIC` (`REVOKE CREATE ON SCHEMA public
  FROM PUBLIC`, por defecto desde PostgreSQL 15, pero se hace explícito).
- **Quién crea los roles:** una función idempotente `provision_roles(admin_engine, passwords)`
  (módulo `storage/roles.py`), que usa `psycopg.sql` para escribir contraseñas como literales
  seguros (DDL no admite parámetros). Si el rol existe, solo actualiza su contraseña (permite rotarla).
  La usan los tests, la CI y Compose, así que hay **una sola implementación**.
- **Quién concede los permisos:** la migración `0001` ejecuta los `GRANT` sobre `events`. Si falta un
  rol, falla con un mensaje claro que pide ejecutar el aprovisionamiento (no omite los permisos en
  silencio).
- **Alternativas:** script de inicialización de la imagen de PostgreSQL (solo corre en un volumen
  vacío y duplicaría la lógica de los tests), un único rol (descartado en la clarificación), `GRANT`
  fuera de la migración (dos pasos que pueden desincronizarse).

## R8. Migraciones

- **Decisión:** revisión `0001_create_events` escrita a mano (sin autogeneración) en
  `storage/migrations/versions/`. `env.py` pasa a leer `MIGRATION_DATABASE_URL` (rol migrador).
- **Revertir es destructivo:** `downgrade()` borra `events`; se niega si la tabla tiene filas salvo
  que se pase `-x destructive=yes` (Principio VII: requiere autorización explícita). Un test lo cubre.
- **Idempotencia:** Alembic ya registra la revisión; volver a aplicarla no hace nada (FR-002-05).
- **Alternativas:** autogeneración (podría arrastrar diferencias), `downgrade` sin guardia.

## R9. Configuración

- **Decisión:** modelos Pydantic cargados con `load_model` (incremento 1), sin tocar `Settings`:

| Variable | Modelo | Uso |
|---|---|---|
| `DATABASE_URL` | `Settings` (existente) | la API; pasa a ser el rol `anomaly_app` |
| `MIGRATION_DATABASE_URL` | `MigrationSettings` | Alembic (rol migrador) |
| `MAINTENANCE_DATABASE_URL` | `MaintenanceSettings` | purga (rol de mantenimiento) |
| `ADMIN_DATABASE_URL` | `AdminSettings` | solo el aprovisionamiento de roles |
| `RETENTION_DAYS`, `QUERY_DEFAULT_LIMIT`, `QUERY_MAX_LIMIT` | `StoragePolicy` | políticas |

  Todas las URL son secretas (`SecretStr`) y los errores nombran la variable, nunca el valor.
- **Racional:** cada operación solo carga las credenciales que necesita; la API no ve nunca las de
  mantenimiento ni las del administrador (FR-002-22).

## R10. Operación: CLI mínima y Compose

- **Decisión (no estaba pedida; aprobada por el usuario el 2026-11-22):** una CLI mínima
  `python -m security_anomaly.storage` (solo `argparse`, sin dependencias) con dos subcomandos:
  `provision-roles` y `purge [--days N] [--dry-run]`. Es la forma de que una **persona** ejecute la
  purga con las credenciales del rol de mantenimiento (FR-002-20, historia 4); sin ella solo se
  podría llamar desde código.
- **Compose:** dos servicios de un solo uso bajo perfiles, que **no** arrancan con `docker compose up`:
  - `db-setup` (perfil `setup`): `provision-roles` y `alembic upgrade head`.
  - `db-maintenance` (perfil `maintenance`): `purge`, por defecto con `--dry-run`.
  La API conecta con el rol `anomaly_app`. Hasta que se ejecuta `db-setup`, `/ready` responde 503
  (la base de datos aún no tiene el rol), coherente con el arranque tolerante del incremento 0.
- **Racional:** la spec fija que las migraciones las ejecuta el operador de forma explícita y que la
  purga nunca es automática. Usar perfiles evita que se ejecuten solas.
- **Alternativas:** script de `docker-entrypoint-initdb.d` (solo primer arranque), migrar al arrancar
  la API (la API tendría credenciales de DDL), sin CLI (la purga no sería utilizable).

## R11. Errores y logs

- **Decisión:** `StorageError` con un `code` estable (`unavailable`, `permission_denied`,
  `integrity`, `unknown`) derivado del SQLSTATE y un mensaje fijo; la excepción original se descarta
  (`from None`). Nunca incluye credenciales, valores ni la sentencia con parámetros (FR-002-25).
- **Logs:** un registro por operación con recuentos, duración e identificador de lote
  (`events_saved`, `events_queried`, `events_purged`); de los filtros solo se registra **qué campos**
  se usaron, nunca sus valores (FR-002-26).

## R12. Rotación de `PSEUDONYM_KEY` (ADR 0003)

- **Decisión:** una única clave durante la vida de los datos (clarificación). El ADR documenta:
  1. Rotar cambia los seudónimos y los `event_id` del adaptador de Linux auth, así que reingerir
     tras rotar **no es idempotente** (se inserta como eventos nuevos).
  2. El nombre original no se guarda, así que los datos ya almacenados **no se pueden
     reseudonimizar**.
  3. Procedimiento: detener la ingesta → purgar los datos seudonimizados con la clave anterior (o
     aceptar explícitamente que el comportamiento por usuario queda partido) → rotar la clave →
     reanudar y, si hace falta, reingerir desde la fuente.
  4. Coste: se pierde el histórico por usuario anterior a la rotación.
  5. Evolución: si hiciera falta rotar sin perder historia, se añadiría una columna de versión de
     clave con una migración.
- Un test de integración refleja el comportamiento observable (el mismo `auth.log` ingerido con dos
  claves inserta dos veces; con el procedimiento, queda solo el nuevo).

## R13. Pruebas

- **Unitarias (sin servicios):** validación de `EventFilter` y de `StoragePolicy`, construcción de
  consultas (todas con parámetros enlazados, ningún valor literal en el SQL compilado), traducción
  de errores a `StorageError`, comparación de contenido, troceado de lotes, cálculo del `cutoff`.
- **Integración (PostgreSQL real, marcador `integration`):** una base de datos efímera por sesión
  (`CREATE DATABASE`), roles aprovisionados con contraseñas aleatorias, migraciones aplicadas con
  Alembic y la tabla vaciada entre tests. Cubren idempotencia, concurrencia (varios hilos),
  atomicidad (fallo a mitad de un lote), consultas y paginación, lectura por rango sin fuga,
  purga y simulación, privilegios de los tres roles (SC-007), migración (aplicar dos veces,
  `downgrade` protegido) y rendimiento (SC-001 y SC-004).
- **CI:** el job `integration` existente aprovisiona los roles antes de migrar; el job
  `compose-smoke` ejecuta `db-setup` antes de comprobar `/ready`.
