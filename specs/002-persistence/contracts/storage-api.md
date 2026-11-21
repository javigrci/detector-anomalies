# Contrato: API pública de la persistencia

La consumen el incremento 3 (características) y el 5 (API). Todo se importa de
`security_anomaly.storage`. Cada función recibe un `Engine` de SQLAlchemy ya creado con el rol que le
corresponde; la API nunca guarda credenciales.

## Funciones

```python
save_events(engine: Engine, events: Iterable[NormalizedEvent], *,
            batch_id: UUID | None = None) -> SaveSummary
```
**Rol:** `anomaly_app`. Guarda los eventos de `IngestionResult.events` de forma idempotente por
`(source, event_id)` y atómica (todo o nada). Sin `batch_id` genera uno. No modifica los eventos que
ya existen.

```python
query_events(engine: Engine, filters: EventFilter | None = None, *,
             limit: int | None = None, offset: int = 0,
             policy: StoragePolicy | None = None) -> EventPage
```
**Rol:** `anomaly_app`. Conjunción de filtros, orden `timestamp, source, event_id` y paginación por
tamaño y desplazamiento. `limit=None` usa el valor por defecto de la política. Valida antes de
consultar: `limit` entre 1 y el máximo, `offset ≥ 0`.

```python
read_range(engine: Engine, start: datetime, end: datetime, *,
           chunk_size: int = 5000) -> Iterator[tuple[StoredEvent, ...]]
```
**Rol:** `anomaly_app`. Lee `[start, end)` en orden cronológico por bloques de como máximo
`chunk_size`, con paginación por clave: sin duplicados ni saltos y con memoria acotada. **Nunca
devuelve un evento con `timestamp >= end` ni `< start`.** `start` y `end` deben tener zona horaria y
`start < end`.

```python
purge_events(engine: Engine, *, retention_days: int | None = None, dry_run: bool = False,
             now: datetime | None = None, policy: StoragePolicy | None = None) -> PurgeResult
```
**Rol:** `anomaly_maint`. Borra los eventos con `ingested_at < now − retention_days` (por defecto la
hora de la base de datos y 90 días), por bloques de 5.000 y una transacción por bloque. Con
`dry_run=True` solo cuenta. `retention_days < 1` → `ValueError` sin tocar la base de datos. Repetir la
purga borra 0.

```python
provision_roles(admin_engine: Engine, passwords: RolePasswords) -> None
```
**Rol:** administrador de PostgreSQL. Crea o actualiza los tres roles y sus privilegios base de forma
idempotente. Lo usan los tests, la CI y Compose.

## Garantías

- **Parámetros:** ninguna consulta se construye con datos de entrada; todo valor es un parámetro
  enlazado.
- **Idempotencia y atomicidad:** guardar dos veces lo mismo no cambia nada; un fallo deja el lote sin
  guardar.
- **Sin fuga de futuro:** `read_range` es semiabierto por arriba.
- **Privacidad:** el almacenamiento solo contiene seudónimos; los filtros solo aceptan seudónimos.
- **Errores y logs:** `StorageError` sin credenciales, valores ni sentencias; los logs solo llevan
  recuentos, duraciones e identificadores de lote.

## Excepciones

| Excepción | Cuándo | Atributos |
|---|---|---|
| `StorageError` | falla la base de datos | `code` ∈ `unavailable`, `permission_denied`, `integrity`, `unknown` |
| `ValueError` / `ValidationError` | filtros o parámetros inválidos, antes de consultar | mensaje sin valores |
| `ConfigError` | configuración inválida (heredada del incremento 1) | mensaje sin valores |

## Correspondencia con SPEC (para el incremento 5)

- `query_events` → `GET /api/v1/events` y `GET /api/v1/anomalies` (filtros y paginación).
- `StorageError(unavailable)` → `503`; `ValidationError` → `422`.
- La API **no** tiene acceso a `purge_events` (otras credenciales).
