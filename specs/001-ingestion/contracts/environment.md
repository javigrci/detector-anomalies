# Contrato de entorno de la ingesta

Se suman a las del [incremento 0](../../000-base/contracts/environment.md). La ingesta no depende de
`DATABASE_URL`: se configura con `IngestionPolicy.from_environ()` y `Pseudonymizer.from_environ()`.

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `PSEUDONYM_KEY` | Sí, si hay usuarios que seudonimizar | — | Secreto de al menos 32 caracteres para el HMAC; se rechaza si contiene `change-me`. Nunca en el repositorio |
| `INGEST_MAX_FILE_BYTES` | No | `10485760` | Tamaño máximo de archivo (10 MB) |
| `INGEST_MAX_EVENTS_PER_BATCH` | No | `10000` | Eventos máximos por lote |
| `INGEST_MAX_EVENTS_PER_DATASET` | No | `100000` | Máximo del dataset sintético |
| `INGEST_MAX_FIELD_LENGTH` | No | `256` | Longitud máxima de un campo de texto |
| `INGEST_TIMESTAMP_MIN` | No | `2000-01-01T00:00:00+00:00` | Inicio del rango válido (ISO 8601 con zona) |
| `INGEST_TIMESTAMP_MAX` | No | `2100-01-01T00:00:00+00:00` | Fin del rango válido (ISO 8601 con zona) |

Reglas: los valores vacíos se tratan como ausentes; los errores de validación nombran la variable y
nunca su valor; `PSEUDONYM_KEY` se guarda como secreto y no se escribe en logs, errores ni informes.
`.env.example` incluye `PSEUDONYM_KEY` con un marcador `change-me-…` sin valor real.

**Rotación de clave:** cambiar `PSEUDONYM_KEY` cambia los seudónimos y los identificadores
derivados, de modo que reingerir los mismos datos tras rotarla no es idempotente (research R6).
