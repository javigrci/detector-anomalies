# Data Model: Persistencia de eventos

Tabla relacional `events` más modelos en memoria (Pydantic v2, inmutables). Las `CHECK` de la tabla
son una fotografía del catálogo v1 del incremento 1 (ver [research R1](research.md)).

## Tabla `events`

| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| `source` | `TEXT` | No | `^[a-z0-9][a-z0-9-]{0,63}$` |
| `event_id` | `TEXT` | No | 1–256 caracteres |
| `timestamp` | `TIMESTAMPTZ` | No | se devuelve en UTC |
| `event_type` | `TEXT` | No | `authentication`, `privilege_escalation`, `other` |
| `action` | `TEXT` | No | `login`, `invalid_user`, `sudo`, `other` |
| `outcome` | `TEXT` | No | `success`, `failure`, `unknown` |
| `user_pseudonym` | `TEXT` | Sí | `^usr_[0-9a-f]{32}$` |
| `source_ip` | `INET` | Sí | IPv4 o IPv6; compara por valor |
| `host` | `TEXT` | Sí | ≤ 256 caracteres |
| `ingested_at` | `TIMESTAMPTZ` | No | `DEFAULT now()`; no cambia nunca tras insertar |
| `batch_id` | `UUID` | No | identificador del guardado |

- **Clave primaria:** `(source, event_id)` (FR-002-04).
- **Sin** `username`, `out_of_order` ni `position`.

### Índices

| Nombre | Columnas | Notas |
|---|---|---|
| `events_pkey` | `(source, event_id)` | |
| `ix_events_timestamp` | `(timestamp, source, event_id)` | orden total, rango y paginación por clave |
| `ix_events_source_timestamp` | `(source, timestamp)` | |
| `ix_events_ip_timestamp` | `(source_ip, timestamp)` | parcial: `WHERE source_ip IS NOT NULL` |
| `ix_events_user_timestamp` | `(user_pseudonym, timestamp)` | parcial: `WHERE user_pseudonym IS NOT NULL` |
| `ix_events_ingested_at` | `(ingested_at)` | purga |

## Roles y privilegios

| Rol | `events` | Esquema `public` | Otros |
|---|---|---|---|
| `anomaly_migrator` | propietario (todo) | `CREATE`, `USAGE` | ejecuta Alembic |
| `anomaly_app` | `SELECT`, `INSERT` | `USAGE` | sin `UPDATE`, `DELETE`, `TRUNCATE` ni DDL |
| `anomaly_maint` | `SELECT`, `DELETE` | `USAGE` | sin `INSERT`, `UPDATE`, `TRUNCATE` ni DDL |

`PUBLIC` no tiene `CREATE` en `public`. Los tres roles tienen `CONNECT` en la base de datos.

## Modelos en memoria (`schemas/storage.py`)

### EventFilter (entrada de la consulta)

| Campo | Tipo | Regla |
|---|---|---|
| `date_from` | `datetime \| None` | con zona horaria; inclusivo |
| `date_to` | `datetime \| None` | con zona horaria; exclusivo; `date_from < date_to` si ambos |
| `source` | `str \| None` | formato de `source` |
| `event_type` | `EventType \| None` | solo valores del catálogo |
| `action` | `Action \| None` | solo valores del catálogo |
| `outcome` | `Outcome \| None` | solo valores del catálogo |
| `source_ip` | `str \| None` | IP válida; se normaliza a forma comprimida |
| `user_pseudonym` | `str \| None` | solo el formato `usr_…` (nunca un nombre real) |

Los filtros presentes se combinan con conjunción.

### StoredEvent

`source`, `event_id`, `timestamp` (UTC), `event_type`, `action`, `outcome`, `user_pseudonym`,
`source_ip`, `host`, `ingested_at` (UTC), `batch_id`.

### EventPage

`items: tuple[StoredEvent, ...]`, `total`, `limit`, `offset`.

### SaveSummary

`batch_id`, `inserted`, `existing`, `existing_with_different_content`.
Invariante: `inserted + existing == número de eventos de entrada`. Los eventos repetidos **dentro
de la propia entrada** se colapsan en Python (gana el primero) y cuentan como `existing`.

### PurgeResult

`retention_days`, `cutoff` (UTC), `dry_run`, `affected` (eventos que se borrarían en simulación o que
se borraron).

### StoragePolicy

| Campo | Por defecto | Regla |
|---|---|---|
| `retention_days` | 90 | ≥ 1 |
| `query_default_limit` | 100 | ≥ 1 y ≤ `query_max_limit` |
| `query_max_limit` | 1.000 | ≥ 1 |

### Configuración por operación

`MigrationSettings` (`MIGRATION_DATABASE_URL`), `MaintenanceSettings` (`MAINTENANCE_DATABASE_URL`) y
`AdminSettings` (`ADMIN_DATABASE_URL` más las contraseñas de los tres roles). Todas las URL y
contraseñas son `SecretStr`; las contraseñas deben tener al menos 12 caracteres y no contener el
marcador `change-me`.

### StorageError

`code ∈ {unavailable, permission_denied, integrity, unknown}` y un mensaje fijo. Sin valores,
credenciales ni sentencias.

## Estados

El único dato con ciclo de vida es el evento: **insertado** (con `ingested_at`) → **purgado**
(cuando supera la retención). No hay actualizaciones.
