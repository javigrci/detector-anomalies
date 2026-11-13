# Data Model: Base del repositorio

Este incremento no tiene modelo de datos persistente (sin tablas). Solo hay estructuras en memoria.

## Settings (configuración)
| Campo | Tipo | Regla |
|---|---|---|
| `app_env` | enum `development` \| `test` \| `production` | por defecto `development` |
| `log_level` | enum `DEBUG`/`INFO`/`WARNING`/`ERROR` | por defecto `INFO` |
| `database_url` | `SecretStr` | obligatoria; esquema `postgresql+psycopg://`; nunca se imprime |
| `db_connect_timeout_s` | int 1–30 | por defecto 2 |
| `api_port` | int 1–65535 | por defecto 8000 |

- Se valida una sola vez al arrancar; si falla, el proceso termina con código distinto de 0 y un mensaje que nombra la variable y el tipo de error, sin el valor.
- Los valores vacíos o con solo espacios se tratan como ausentes.

## RequestId
- Cadena de 1 a 64 caracteres `[A-Za-z0-9._-]`; recibida válida o generada (UUID4).
- Ciclo de vida: nace con la petición, se propaga a logs y cabecera `X-Request-ID`, termina con la respuesta.

## ProbeStatus
| Sonda | Campos |
|---|---|
| `/health` | `status: "ok"` |
| `/ready` (éxito) | `status: "ready"`, `checks.database: "ok"` |
| `/ready` (fallo) | sobre de error con `code: "not_ready"` y `details.checks.database: "unavailable"` |

## ErrorEnvelope
`code` (string estable), `message` (string seguro), `request_id` (string), `details` (objeto, puede estar vacío; nunca trazas ni valores de configuración).

## LogRecord
`timestamp` (UTC ISO 8601), `level`, `logger`, `message`, `request_id` (si existe), más campos extra no sensibles.
