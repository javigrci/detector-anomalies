# Security Log Anomaly Detector

Prototipo de apoyo al análisis de seguridad (SOC): ingerirá logs de auditoría, los puntuará con
Isolation Forest y expondrá los resultados por API REST.

> **Estado: incrementos 0, 1, 2, 3 y 4.** Existen el esqueleto del servicio (sondas `/health` y `/ready`,
> configuración, logging estructurado, Docker Compose y CI), la **biblioteca de ingesta y
> normalización de logs** y la **persistencia de eventos en PostgreSQL** (guardado idempotente,
> consulta, retención y tres roles de BD) y las **características causales** del modelo (por evento y por
> ventana de 5 minutos) y el **entrenamiento del modelo** (Isolation Forest calibrado, evaluado y
> versionado, con activación manual). Todavía no hay API de negocio ni autenticación.
>
> Una anomalía no implica un ataque, y el `anomaly_score` futuro no es una probabilidad de
> intrusión. Los datos sintéticos validan el software, no la capacidad real de detección.

Documentación del proyecto: [constitución](.specify/memory/constitution.md) ·
[SPEC.md](SPEC.md) · [roadmap](docs/roadmap.md) · [decisiones](docs/decisions/) ·
[contrato de datos](docs/data-contract.md) ·
[especificación del incremento 0](specs/000-base/spec.md) ·
[especificación del incremento 1](specs/001-ingestion/spec.md) ·
[especificación del incremento 2](specs/002-persistence/spec.md) ·
[especificación del incremento 3](specs/003-feature-engineering/spec.md) ·
[especificación del incremento 4](specs/004-model-training/spec.md)

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 y las dependencias).
- Docker con Compose. En Windows con WSL2, activa la integración de Docker Desktop con tu
  distribución (Settings → Resources → WSL integration).

## Instalación

```bash
uv sync --frozen
```

`--frozen` instala exactamente lo fijado en `uv.lock` y falla si `pyproject.toml` y el lock no
coinciden.

## Configuración

```bash
cp .env.example .env
```

Edita `.env` y sustituye **todas** las contraseñas `change-me-…`: `POSTGRES_PASSWORD` (administrador de
PostgreSQL) y las tres de los roles de la aplicación, que deben ser **distintas entre sí**
(`MIGRATOR_DB_PASSWORD`, `APP_DB_PASSWORD`, `MAINT_DB_PASSWORD`; por ejemplo `openssl rand -hex 12`), y
las mismas claves dentro de las URL si ejecutas fuera de Compose. Las claves deben ser aptas para URL:
sin `@ : / ? # %`. `.env` está excluido de
Git; nunca lo subas. Las variables están descritas en
[specs/000-base/contracts/environment.md](specs/000-base/contracts/environment.md).

Si falta una variable obligatoria o es inválida, el servicio termina con un mensaje que nombra la
variable y nunca muestra su valor.

## Arrancar y detener

```bash
docker compose up --build -d --wait   # API + PostgreSQL 16
docker compose down                   # detener (añade -v para borrar también los datos)
```

La API queda en `http://127.0.0.1:${API_PORT:-8000}` (solo accesible desde tu máquina). La base de
datos no se publica en el host. Si el puerto está ocupado, cambia `API_PORT` en `.env`.

La API arranca aunque la base de datos no esté disponible: `/health` responde igualmente y
`/ready` indica no disponible hasta que la base de datos responda.

**Primer arranque (incremento 2):** la API usa el rol `anomaly_app`, que aún no existe, así que `/ready`
responde 503 hasta ejecutar el aprovisionamiento. Los servicios `db-setup` y `db-maintenance` van bajo
perfiles y **no** arrancan con `up`:

```bash
docker compose --profile setup run --rm db-setup                         # roles + migraciones → /ready 200
docker compose --profile maintenance run --rm db-maintenance             # simulación de purga
docker compose --profile maintenance run --rm db-maintenance purge       # borra de verdad
```

## Sondas

| Ruta | Respuesta | Significado |
|---|---|---|
| `GET /health` | `200 {"status":"ok"}` | El proceso está vivo; no consulta la base de datos. |
| `GET /ready` | `200 {"status":"ready","checks":{"database":"ok"}}` | Listo para recibir tráfico. |
| `GET /ready` | `503` con `code: "not_ready"` | La base de datos no responde. |

Son públicas y están fuera del prefijo `/api/v1`. Documentación interactiva en `/docs` y esquema
en `/openapi.json`.

Cada respuesta incluye la cabecera `X-Request-ID`. Si envías una válida (`[A-Za-z0-9._-]`, de 1 a
64 caracteres) se conserva; si no, se genera un UUID. El mismo identificador aparece en el cuerpo
de los errores y en los logs, que son JSON por línea a stdout (`docker compose logs api`).

Todos los errores usan el formato `{"code", "message", "request_id", "details"}`.

## Verificación en local

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mypy tests
uv run pytest -m "not integration"
```

### Tests de integración (PostgreSQL real)

Necesitan una base de datos. Levanta una temporal con una clave aleatoria que solo vive en tu
terminal:

```bash
export PGPW="$(openssl rand -hex 12)"
docker run --rm -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD="$PGPW" postgres:16
export DATABASE_URL="postgresql+psycopg://postgres:${PGPW}@127.0.0.1:55432/postgres"
uv run pytest -m integration
docker stop pg-test
```

## Ingesta de logs (biblioteca)

`security_anomaly.ingestion` lee JSON (lista o JSON Lines) y CSV, convierte `auth.log` clásico de
Linux, valida y normaliza los eventos, seudonimiza el usuario y devuelve un informe con aceptados,
rechazados, duplicados, fuera de orden e ignorados. No tiene interfaz: los incrementos siguientes la
consumen como funciones. Contrato de datos completo en [docs/data-contract.md](docs/data-contract.md).

```python
from pathlib import Path

from security_anomaly.ingestion import IngestionPolicy, Pseudonymizer, ingest_file

result = ingest_file(
    Path("events.json"),
    policy=IngestionPolicy.from_environ(),
    pseudonymizer=Pseudonymizer.from_environ(),
)
print(result.report.accepted, result.report.rejected)
```

Necesita `PSEUDONYM_KEY` (mínimo 32 caracteres aleatorios; `openssl rand -hex 32`). Los límites y el
rango de fechas se configuran con las variables `INGEST_*` de `.env.example`. El informe contiene
solo códigos, campos, posiciones y recuentos, nunca valores de entrada. Para `auth.log` se usa
`ingest_linux_auth(path, policy=…, pseudonymizer=…, start_year=2026, tz=ZoneInfo("Europe/Madrid"))`;
`generate_synthetic` produce eventos sintéticos reproducibles con etiquetas aparte.

## Persistencia (biblioteca y CLI)

`security_anomaly.storage` guarda los eventos normalizados en PostgreSQL y los consulta. No tiene
endpoints (llegan en el incremento 5). Cada función recibe un `Engine` de SQLAlchemy creado con el rol
que le corresponde; contrato completo en
[specs/002-persistence/contracts/storage-api.md](specs/002-persistence/contracts/storage-api.md).

```python
from sqlalchemy import create_engine

from security_anomaly.storage import EventFilter, query_events, read_range, save_events

engine = create_engine(DATABASE_URL)  # rol anomaly_app
summary = save_events(engine, result.events)  # idempotente por (source, event_id) y atómico
page = query_events(engine, EventFilter(outcome="failure"), limit=100, offset=0)
for chunk in read_range(engine, start, end):  # [start, end): nunca devuelve timestamp >= end
    ...
```

- **Tres roles de BD con mínimos privilegios:** `anomaly_migrator` (propietario del esquema, solo
  migraciones), `anomaly_app` (solo insertar y consultar) y `anomaly_maint` (solo borrar eventos, para la
  purga). La aplicación no puede alterar el esquema ni borrar datos.
- **Solo se guarda el seudónimo del usuario**, nunca el nombre original. Rotar `PSEUDONYM_KEY` tiene
  consecuencias: ver [docs/decisions/0003-rotacion-pseudonym-key.md](docs/decisions/0003-rotacion-pseudonym-key.md).
- **Retención:** 90 días por defecto (`RETENTION_DAYS`), contados desde la **ingesta** del evento, no desde
  su `timestamp`. Nunca se purga sola; la purga es una acción explícita con credenciales propias.
- **Paginación por tamaño y desplazamiento:** si se insertan eventos entre dos páginas, estas pueden
  desplazarse. Para lecturas largas que necesitan exactitud se usa `read_range`.
- Los datos de ejemplo y de los tests son **sintéticos**: nada de lo guardado en el repositorio es
  tráfico real.

CLI de operación (solo `argparse`; una línea JSON con recuentos, nunca valores ni credenciales):

```bash
python -m security_anomaly.storage provision-roles       # ADMIN_DATABASE_URL + 3 contraseñas
python -m security_anomaly.storage purge --dry-run        # MAINTENANCE_DATABASE_URL, RETENTION_DAYS
python -m security_anomaly.storage purge --days 30
```

Códigos de salida: `0` correcto, `2` configuración o argumentos inválidos, `1` error de base de datos.

## Características (biblioteca)

`security_anomaly.features` convierte eventos en vectores de características para el modelo del
incremento 4: por evento (hora UTC cíclica, día de la semana, tipo, acción, resultado y fuente) y por
ventana deslizante de 5 minutos (eventos, fallos, tasa de fallos y usuarios distintos por IP; IPs distintas
por usuario). No tiene interfaz ni guarda nada. Esquema completo en
[specs/003-feature-engineering/contracts/feature-schema.md](specs/003-feature-engineering/contracts/feature-schema.md).

```python
from datetime import UTC, datetime

from security_anomaly.features import compute_event_features, compute_features, features_for_range

history_start = datetime(2026, 1, 1, tzinfo=UTC)  # desde cuándo hay historia completa
vectors = compute_features(events, history_start=history_start)  # un conjunto (entrenamiento)
vector = compute_event_features(
    event, previous, history_start=history_start
)  # un evento (inferencia)
rango = features_for_range(engine, start, end, history_start=history_start)  # leído de PostgreSQL
```

- **Sin fuga de futuro:** el vector de un evento solo usa los eventos que lo preceden en el orden total
  `(timestamp, source, event_id)` más él mismo, dentro de `(t - 5 min, t]`. Añadir, quitar o modificar
  eventos posteriores no cambia ningún vector (ADR 0004).
- **Mismo pipeline:** lotes, evento individual y rango usan el mismo motor y dan el mismo vector.
- **Esquema versionado:** versión y huella fijadas en un test; los vectores nunca llevan IP, usuario, host
  ni `event_id` como característica.
- `context_complete` es falso cuando la ventana empieza antes de `history_start` (lo declara quien llama).
- Las características describen comportamiento, no demuestran que haya un ataque, y los datos de ejemplo
  y de los tests son **sintéticos**.

## Entrenamiento del modelo (biblioteca y CLI)

`security_anomaly.ml` entrena el detector con los vectores de características del incremento 3: ordena los
datos en el tiempo y los separa en **entrenamiento** (70 % más antiguo), **calibración** (15 %) y **prueba**
(15 % más reciente); ajusta las transformaciones y un Isolation Forest (semilla 42) **solo** con el
entrenamiento y calibra con el conjunto de calibración. No tiene API todavía (llega en el incremento 5).
Contrato completo en [specs/004-model-training/contracts/ml-api.md](specs/004-model-training/contracts/ml-api.md).

- **`anomaly_score` no es una probabilidad de ataque:** es el percentil de la puntuación bruta frente a la
  distribución de calibración (de 0 a 1). La severidad (`low`, `medium`, `high`) usa umbrales provisionales
  de 0,80 y 0,95, configurables y por validar. Decide siempre una persona.
- **Evaluación y límites:** el informe muestra la distribución de puntuaciones, su estabilidad en el tiempo y la
  proporción de alertas; con etiquetas externas añade precision, recall, F1 y PR-AUC. **No se promete ninguna
  precisión mínima** y los datos de ejemplo son **sintéticos**: validan el software, no la detección real.
- **Cada modelo queda versionado** (`v0001`, `v0002`…) con su esquema de características, parámetros, fecha,
  métricas y la huella del dataset, en un archivo del directorio interno `MODEL_DIR` y en las tablas
  `training_runs` y `model_versions`. Los registros no se pueden modificar salvo para activarlos.
- **Un modelo solo se carga de `MODEL_DIR` y después de verificar su huella SHA-256**: nunca de una ruta
  recibida de un usuario.
- **Entrenar nunca activa.** Activar exige aprobación explícita y solo hay una versión activa a la vez.
  Solo puede haber un entrenamiento en curso.

```bash
export MODEL_DIR=/var/lib/anomaly/models                      # directorio interno de confianza (ya creado)
python -m security_anomaly.ml train --start 2026-01-01T00:00:00+00:00 --end 2026-02-01T00:00:00+00:00
python -m security_anomaly.ml status                           # estado de los entrenamientos recientes
python -m security_anomaly.ml list                             # versiones registradas
python -m security_anomaly.ml activate v0001 --approve         # activación manual
```

Cada orden imprime una línea JSON; códigos de salida `0` correcto, `2` configuración o argumentos inválidos,
`1` error controlado. Las variables (umbrales, fracciones, árboles) están en `.env.example`. El modelo usa
`scikit-learn` ([ADR 0005](docs/decisions/0005-scikit-learn.md)); la confianza de los artefactos y la
concurrencia están en el [ADR 0006](docs/decisions/0006-confianza-de-artefactos-y-concurrencia.md).

## Migraciones

El esquema solo lo crea Alembic, con el rol migrador (`MIGRATION_DATABASE_URL`); el servicio **nunca**
migra al arrancar. Primero hay que aprovisionar los roles:

```bash
uv run python -m security_anomaly.storage provision-roles
uv run alembic upgrade head                                 # crea la tabla `events` (0001); repetirlo no cambia nada
uv run alembic -x destructive=yes downgrade base            # DESTRUCTIVO: borra los eventos; pide autorización explícita
```

`downgrade` se niega si la tabla tiene filas salvo con `-x destructive=yes`.

## Integración continua

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) se ejecuta en cada push a `main` y en cada
pull request, con tres jobs:

1. `quality`: Ruff (lint y formato), mypy y tests unitarios.
2. `integration`: aprovisiona los roles, aplica `alembic upgrade head` y ejecuta los tests contra un
   PostgreSQL 16 real.
3. `compose-smoke`: levanta el entorno con Compose, comprueba `/health` y que `/ready` da 503 antes del
   aprovisionamiento, ejecuta `db-setup` y comprueba `/ready` 200 y la simulación de purga.

## Límites conocidos

- La CI informa del resultado pero **no puede bloquear** la integración: comprobado el 2026-11-13,
  GitHub responde 403 («Upgrade to GitHub Pro or make this repository public») al consultar la
  protección de rama de este repositorio privado. Hasta que eso cambie, la regla se cumple por
  proceso: no integrar cambios con la CI en rojo.
- Los tiempos de referencia (`/ready` en unos 3,6 s con la base de datos caída, recuperación en
  1 s) se midieron en una máquina de desarrollo con WSL2 y Docker Desktop; no son garantías.
