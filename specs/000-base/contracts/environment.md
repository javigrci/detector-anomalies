# Contrato de entorno

Variables leídas por la aplicación. `.env.example` las contiene todas, con valores de desarrollo y
sin secretos reales; `.env` está excluido de Git.

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `APP_ENV` | No | `development` | `development`, `test` o `production` |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DATABASE_URL` | Sí | — | `postgresql+psycopg://usuario:clave@host:5432/base`; contiene secreto |
| `DB_CONNECT_TIMEOUT_S` | No | `2` | Timeout de conexión de las sondas (1–30) |
| `API_PORT` | No | `8000` | Puerto del proceso; en Compose, también el publicado en `127.0.0.1` |

Variables solo de Compose (contenedor de base de datos):

| Variable | Obligatoria | Descripción |
|---|---|---|
| `POSTGRES_USER` | Sí | Usuario de la base de datos |
| `POSTGRES_PASSWORD` | Sí | Clave; apta para URL (sin `@ : / ? # %`). Sin valor por defecto |
| `POSTGRES_DB` | Sí | Nombre de la base de datos |

Reglas: valores vacíos se tratan como ausentes; los errores de validación nombran la variable y
nunca muestran el valor; ningún valor sensible se escribe en logs, errores ni imágenes.
