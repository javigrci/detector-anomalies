# Contrato de entorno de la persistencia

Se suman a las de los incrementos [0](../../000-base/contracts/environment.md) y
[1](../../001-ingestion/contracts/environment.md). Cada operación solo carga las credenciales que
necesita; todas las URL y contraseñas son secretas.

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `DATABASE_URL` | Sí (API) | — | **Cambia de rol:** ahora apunta al rol `anomaly_app` |
| `MIGRATION_DATABASE_URL` | Sí (Alembic) | — | URL del rol `anomaly_migrator`; `postgresql+psycopg://…` |
| `MAINTENANCE_DATABASE_URL` | Sí (purga) | — | URL del rol `anomaly_maint` |
| `ADMIN_DATABASE_URL` | Sí (aprovisionamiento) | — | URL de un administrador de PostgreSQL; solo para `provision-roles` |
| `MIGRATOR_DB_PASSWORD` | Sí (aprovisionamiento y Compose) | — | Contraseña del rol migrador |
| `APP_DB_PASSWORD` | Sí (aprovisionamiento y Compose) | — | Contraseña del rol de aplicación |
| `MAINT_DB_PASSWORD` | Sí (aprovisionamiento y Compose) | — | Contraseña del rol de mantenimiento |
| `RETENTION_DAYS` | No | `90` | Periodo de retención en días (≥ 1), medido desde la ingesta |
| `QUERY_DEFAULT_LIMIT` | No | `100` | Tamaño de página por defecto |
| `QUERY_MAX_LIMIT` | No | `1000` | Tamaño de página máximo |

Reglas:

- Las contraseñas de los tres roles deben ser **distintas**, tener al menos 12 caracteres, ser aptas
  para URL (sin `@ : / ? # %`) y **no contener `change-me`**: el valor de `.env.example` se rechaza
  a propósito.
- Los valores vacíos se tratan como ausentes; los errores nombran la variable y nunca su valor.
- `.env.example` incluye todas con marcadores `change-me-…`; `.env` no se versiona.
- En los **tests de integración** y en el job `integration` de la CI, `DATABASE_URL` es la conexión de
  administrador de PostgreSQL (superusuario de la base de datos efímera): sirve para crear la base de
  datos de prueba y aprovisionar los roles. Los tests construyen las URL de los tres roles al vuelo.
  En Compose y en producción sigue siendo la URL del rol `anomaly_app`.
- La API no recibe nunca `MAINTENANCE_DATABASE_URL`, `ADMIN_DATABASE_URL` ni
  `MIGRATION_DATABASE_URL`.
