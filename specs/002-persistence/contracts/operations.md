# Contrato de operación: migraciones, roles, CLI y Compose

## Migraciones

```bash
alembic upgrade head                      # con MIGRATION_DATABASE_URL (rol anomaly_migrator)
alembic -x destructive=yes downgrade base # destructivo: borra la tabla de eventos
```

- La revisión `0001_create_events` crea la tabla, las `CHECK`, los índices y concede los permisos a
  `anomaly_app` y `anomaly_maint`.
- Si falta algún rol, la migración falla con un mensaje claro que indica ejecutar el aprovisionamiento.
- Aplicar las migraciones dos veces no cambia nada.
- `downgrade` se niega si la tabla tiene filas, salvo con `-x destructive=yes` (autorización
  explícita). El servicio **nunca** migra al arrancar.

## CLI de operación

```bash
python -m security_anomaly.storage provision-roles
python -m security_anomaly.storage purge [--days N] [--dry-run]
```

| Subcomando | Variables necesarias | Qué hace |
|---|---|---|
| `provision-roles` | `ADMIN_DATABASE_URL`, `APP_DB_PASSWORD`, `MAINT_DB_PASSWORD`, `MIGRATOR_DB_PASSWORD` | Crea o actualiza los tres roles y sus privilegios base; idempotente |
| `purge` | `MAINTENANCE_DATABASE_URL`, `RETENTION_DAYS` (opcional) | Borra los eventos anteriores al periodo, o con `--dry-run` informa cuántos |

- Salida: **una línea JSON** en la salida estándar con recuentos (`retention_days`, `cutoff`,
  `dry_run`, `affected`); nunca valores de eventos ni credenciales.
- Códigos de salida: `0` correcto; `2` configuración o argumentos inválidos (el mensaje nombra la
  variable, no su valor); `1` error de base de datos (solo el `code` de `StorageError`).
- `--days` sustituye a `RETENTION_DAYS` y debe ser ≥ 1.

## Compose

| Servicio | Perfil | Comando | Credenciales |
|---|---|---|---|
| `db` | (siempre) | PostgreSQL 16, sin publicar en el equipo | superusuario `POSTGRES_USER` |
| `api` | (siempre) | servicio actual | `DATABASE_URL` → rol `anomaly_app` |
| `db-setup` | `setup` | `provision-roles` y `alembic upgrade head` | administrador y migrador |
| `db-maintenance` | `maintenance` | `purge --dry-run` por defecto | rol `anomaly_maint` |

```bash
docker compose up --build -d --wait                       # db y api; /ready = 503 hasta el setup
docker compose --profile setup run --rm db-setup          # roles y migraciones
docker compose --profile maintenance run --rm db-maintenance purge --dry-run
docker compose --profile maintenance run --rm db-maintenance purge   # borra de verdad
```

Los servicios de los perfiles no arrancan con `up` y terminan al acabar (`run --rm`).

## Privilegios esperados (SC-007)

| Operación | `anomaly_app` | `anomaly_maint` | `anomaly_migrator` |
|---|---|---|---|
| `INSERT` en `events` | ✅ | ❌ | ✅ |
| `SELECT` en `events` | ✅ | ✅ | ✅ |
| `DELETE` en `events` | ❌ | ✅ | ✅ |
| `UPDATE`, `TRUNCATE` en `events` | ❌ | ❌ | ✅ |
| `CREATE`, `ALTER`, `DROP` | ❌ | ❌ | ✅ |
