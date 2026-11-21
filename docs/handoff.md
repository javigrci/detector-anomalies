# Traspaso de sesión y contexto

> **Para quien retome el trabajo (persona o una sesión nueva de Claude Code):** lee este documento
> entero antes de tocar nada. Resume dónde estamos, qué se decidió y por qué, qué falta aprobar y
> cómo preparar un equipo nuevo. Está escrito el **2026-11-21**; si el repositorio ha avanzado,
> contrasta con `git log` y con los `tasks.md` de cada incremento, que mandan sobre este texto.

## 1. Qué es el proyecto

Prototipo de apoyo al análisis de seguridad (SOC) que detecta **comportamiento inusual** en logs de
auditoría: ingiere logs, los normaliza, genera características por ventana temporal, entrena un
**Isolation Forest** (no supervisado), puntúa eventos y los expone por API REST. Se desarrolla con
**Spec-Driven Development** (GitHub Spec Kit) y agentes de IA como desarrolladores; el motor de
detección es ML clásico.

Tres ideas que gobiernan todo (están en la constitución):

- **Una anomalía no es un ataque.** `anomaly_score` no es una probabilidad. Decide siempre una persona.
- **Seguridad y privacidad por diseño:** los logs son datos no confiables; el usuario se guarda solo
  seudonimizado (HMAC); consultas parametrizadas; mínimos privilegios; sin secretos en el repositorio.
- **Reproducibilidad y verdad evidenciada:** tests antes del código, resultados reportados tal como
  salen, nada se declara terminado sin evidencia.

Repositorio: `git@github.com:javigrci/detector-anomalies.git` (**privado**, rama `main`, se trabaja
directamente en `main`). La protección de rama **no está disponible** en el plan gratuito de GitHub
para repos privados (la API devuelve 403): la CI informa pero no puede bloquear fusiones; la regla se
cumple por proceso (no integrar con la CI en rojo).

## 2. Estado actual

| Incremento | Contenido | Estado |
|---|---|---|
| 0 `000-base` | Esqueleto: FastAPI, `/health` y `/ready`, configuración, logging JSON con `request_id`, Docker Compose, CI | ✅ Hecho y en `main` (CI verde, run 43423457154) |
| 1 `001-ingestion` | Biblioteca de ingesta: JSON/CSV, `auth.log` de Linux, normalización, rechazos sin valores, HMAC, datos sintéticos | ✅ Hecho y en `main` (CI verde, run 44780849063) |
| 2 `002-persistence` | PostgreSQL, migración, guardado idempotente, consultas, retención/purga, tres roles de BD | 🟡 **Spec, clarificación y plan hechos; falta `tasks.md`** |
| 3 `003-feature-engineering` | Características por evento y por ventana de 5 min, sin fuga de futuro | ⬜ |
| 4 `004-model-training` | Entrenamiento, calibración, versiones del modelo | ⬜ |
| 5 `005-inference-api` | API de puntuación y consulta, API key con roles `reader`/`admin` | ⬜ |
| 7 `007-deployment` | Compose completo, runbook, model card y prueba de extremo a extremo | ⬜ |
| 6 `006-dashboard` | Dashboard Streamlit (**fuera del MVP**, fase 2) | ⬜ |

Resultado verificado al cerrar el incremento 1: **329 tests unitarios + 2 de integración** (con
PostgreSQL real), Ruff, formato y mypy estricto en verde, sin dependencias nuevas desde el
incremento 0. El MVP son los incrementos 0 a 5 más el 7 (llevamos 2 de 7). Los plazos no se han
medido: solo el orden y las puertas de aceptación son fiables.

## 3. Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Constitución (v1.0.1, 7 principios) | `.specify/memory/constitution.md` |
| Especificación global (v1.1) | `SPEC.md` |
| Reglas operativas para agentes | `AGENTS.md` (`CLAUDE.md` solo importa `AGENTS.md`) |
| Hoja de ruta (MVP y fases) | `docs/roadmap.md` |
| Contrato de datos del evento | `docs/data-contract.md` |
| Decisiones (ADR) | `docs/decisions/0001-decisiones-iniciales.md`, `0002-dependencias-base.md` |
| Una carpeta por incremento | `specs/NNN-nombre/`: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `tasks.md`, `verification.md`, `checklists/` |
| Feature activa de Spec Kit | `.specify/feature.json` (ahora apunta a `specs/002-persistence`) |
| Comandos de Spec Kit para Claude | `.claude/skills/speckit-*` (versionados) |
| Código | `src/security_anomaly/{api,core,ingestion,schemas,storage,…}` |
| Tests y fixtures | `tests/unit`, `tests/integration`, `tests/fixtures/ingestion/` |

## 4. Decisiones tomadas (resumen; el detalle está en los ADR y en cada spec)

**Globales** (ADR 0001, D1 a D8): MVP sin dashboard; specs en carpetas de Spec Kit; orden de
incrementos con la persistencia antes de las características y el entrenamiento; primer formato de
log real = **Linux auth** (Windows Security Event, estudio a largo plazo); eventos fuera de orden se
aceptan y puntúan con lo conocido; ingesta por lotes acepta los válidos e informa los rechazados;
entrenamiento administrativo en proceso aparte (sin Celery ni Redis); usuario como HMAC con retención
configurable de 90 días.

**Dependencias** (ADR 0002): `psycopg` v3, **sin** `pydantic-settings` (configuración propia sobre
Pydantic v2), backend de construcción `uv_build`, acciones `actions/checkout` y `astral-sh/setup-uv`.

**Incremento 1** (clarificaciones): campos desconocidos → se rechaza el registro y su nombre solo se
informa si es un identificador seguro (`<invalid-name>` si no); solo `auth.log` clásico; la
deduplicación es solo **dentro de cada lote** (entre lotes, la persistencia); rango de fechas fijo
`2000-01-01 ≤ t < 2100-01-01` (no depende del reloj); `sudo` correcto y fallido; "fuera de orden" =
anterior al mayor timestamp ya visto en el mismo lote; archivo o lista vacíos = 0 registros sin error;
`PSEUDONYM_KEY` ≥ 32 caracteres y rechaza el marcador `change-me`; los `event_id` del adaptador se
derivan con HMAC (un hash sin clave permitiría un ataque de diccionario contra el usuario).

**Incremento 2** (clarificaciones, ya en la spec): retención contada **desde la fecha de ingesta**
(no desde el `timestamp` del evento, para no purgar datos históricos o sintéticos al cargarlos); una
única clave de seudonimización durante la vida de los datos (rotarla exige purgar antes); **tres roles
de BD**: migrador, aplicación (solo insertar y consultar) y mantenimiento (solo borrar, para la
purga); paginación por tamaño y desplazamiento (SPEC §6.2); sin tabla de lotes.

## 5. Qué falta ahora mismo (empieza aquí)

El incremento 2 tiene spec, plan, investigación, modelo de datos, contratos y quickstart. **Necesita
tu aprobación** antes de `/speckit-tasks` para tres componentes que no estaban pedidos expresamente
(AGENTS.md regla 3; justificados en `specs/002-persistence/research.md` R10):

1. Una **CLI mínima** `python -m security_anomaly.storage` con `provision-roles` y `purge [--days N]
   [--dry-run]` (solo `argparse`): es la forma de que una persona ejecute la purga con las
   credenciales del rol de mantenimiento.
2. Dos **servicios de Compose bajo perfiles** (`db-setup` y `db-maintenance`) que no arrancan con
   `docker compose up`, para que migrar y purgar sean explícitos.
3. **Variables de entorno nuevas**: una URL por rol, tres contraseñas y el periodo de retención.

Consecuencias a recordar: la API en Compose conectará con el rol `anomaly_app` y `/ready` dará 503
hasta ejecutar `db-setup`; el test de integración de Alembic cambia (ahora se crea `events`); y la CI
(`compose-smoke`) tendrá que ejecutar `db-setup`.

Siguiente secuencia del ciclo: aprobar lo anterior → `/speckit-tasks` → `/speckit-analyze` (corregir
lo que salga) → commit → `/speckit-implement` → cierre con `verification.md`. Después, el incremento 3.

## 6. Pendientes y riesgos conocidos

- **Validar el adaptador de `auth.log` con un log real de un servidor.** Los fixtures de Debian/Ubuntu y
  RHEL son sintéticos (escritos a partir del formato conocido); falta contrastar el recuento de líneas
  ignoradas con datos reales.
- **ADR 0003 (rotación de `PSEUDONYM_KEY`)**: se escribe en el incremento 2; lo decidido ya está en la spec.
- **Aviso heredado:** `starlette.testclient` avisa de que `httpx` está en desuso y recomienda `httpx2`.
  No afecta hoy; conviene revisarlo antes del incremento 5.
- **Cobertura mínima de tests:** sin umbral, diferida.
- **Márgenes de rendimiento:** `/ready` con la BD caída responde en ≈3,6 s (objetivo < 5 s, margen corto).
- **Benchmarks:** hardware de referencia y volumen por fijar en los incrementos 4 y 7.
- Límites conocidos de la ingesta: un `auth.log` no cronológico en el cambio de año se interpreta mal.

## 7. Cómo trabajamos (acuerdos con el asistente)

- **Idioma:** español en todo (documentos, commits de especificación, conversación). Los identificadores
  de código, en inglés.
- **Ciclo por incremento:** `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks`
  → `/speckit-analyze` → `/speckit-implement`. Las preguntas se hacen **de una en una**, con una
  recomendación; basta responder "recomendadas".
- **Tests primero** (deben fallar antes de implementar) y resultados reales; si algo falla o se salta,
  se dice. Se hicieron pruebas de mutación cuando un test pasaba sin código nuevo.
- **Commit y push solo con autorización explícita** (Principio VII). En este repositorio privado el
  usuario ha autorizado trabajar directamente en `main`. Los mensajes de commit terminan con la línea
  `Co-Authored-By` que fije el entorno.
- **Sin dependencias nuevas** sin aprobación y registro en un ADR.
- **Nada de secretos** en el repositorio: las claves de prueba se generan al vuelo (`openssl rand -hex 32`)
  y viven solo en la terminal.
- El usuario prefiere explicaciones **sencillas** cuando las pide, y confirma o ajusta las decisiones con
  respuestas cortas.

## 8. Preparar un equipo nuevo

Requisitos: Linux o WSL2 (Ubuntu), `git`, `uv` ≥ 0.11, Docker con Compose (en WSL2: Docker Desktop con la
**integración WSL activada y Docker Desktop abierto**), `gh` autenticado y clave SSH registrada en GitHub.

```bash
git clone git@github.com:javigrci/detector-anomalies.git && cd detector-anomalies
uv sync --frozen                                   # instala Python 3.12 y las dependencias
cp .env.example .env                               # y sustituye TODAS las contraseñas `change-me-…`
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests
uv run pytest -q -m "not integration"              # 329 tests
```

Tests de integración (PostgreSQL real): levanta una temporal con una clave aleatoria que solo vive en tu
terminal.

```bash
export PGPW="$(openssl rand -hex 12)"
docker run --rm -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD="$PGPW" postgres:16
export DATABASE_URL="postgresql+psycopg://postgres:${PGPW}@127.0.0.1:55432/postgres"
uv run pytest -q -m integration
docker stop pg-test
```

Entorno completo: `docker compose up --build -d --wait` y `curl http://127.0.0.1:8000/health` (y `/ready`).

Para trabajar con Claude Code: abre el repositorio en el equipo nuevo; los comandos `/speckit-*` ya
vienen en `.claude/skills/`. Pídele que lea este documento, `AGENTS.md` y el `tasks.md` del incremento
en curso. Para marcar tareas hechas basta sustituir `- [ ] Txxx` por `- [X] Txxx` en el `tasks.md`.

## 9. Trampas conocidas

- **Docker Desktop cerrado** → `docker` falla o no existe dentro de WSL. Ábrelo antes de empezar.
- **Un comando largo con muchos archivos escritos con `heredoc`** fue bloqueado una vez por el filtro de
  seguridad de Claude Code (falso positivo sobre borrados). Se resolvió creando los archivos con la
  herramienta de escritura, uno a uno.
- Las rutas del directorio temporal de la sesión (`/tmp/claude-…/scratchpad`) **no persisten**: los
  scripts auxiliares (marcar tareas, levantar PostgreSQL temporal) hay que recrearlos; las recetas están
  arriba.
- `uv sync --frozen` falla si `pyproject.toml` y `uv.lock` no coinciden: es intencionado.
- Si `/ready` da 503 con la BD arriba, revisa que `DATABASE_URL` apunte al host `db` (en Compose) y que
  la clave sea apta para URL (sin `@ : / ? # %`).

## 10. Qué NO está en el repositorio (y cómo llevarlo)

- **`.env`** (excluido a propósito): créalo en cada equipo desde `.env.example` con claves nuevas.
- **La transcripción de la conversación**: vive solo en el equipo original, en
  `~/.claude/projects/-home-user-test-detector-anomalies/*.jsonl` (≈7 MB) y **no se ha versionado**
  porque puede contener salidas de herramientas con datos de entorno. Si quieres conservarla, cópiala
  tú por un canal privado (`scp` o un USB); no hace falta para retomar el trabajo, porque las decisiones
  están en las specs, los ADR y este documento.
- **La memoria local de Claude** (`~/.claude/projects/…/memory/`): es por equipo; este documento hace
  de equivalente portátil.
