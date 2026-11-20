# Implementation Plan: Ingesta y normalización de logs

**Branch**: `001-ingestion` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-ingestion/spec.md`

## Summary

Biblioteca de ingesta sin interfaz: lee JSON y CSV en el esquema v1, convierte `auth.log` clásico de
Linux, valida y normaliza de forma determinista, seudonimiza el usuario con HMAC, aplica los límites
de calidad y devuelve un informe por lote (válidos, rechazados, duplicados, fuera de orden,
ignorados). Incluye un generador de eventos sintéticos reproducible. Sin persistencia, endpoints,
autenticación ni ML. Decisiones y alternativas en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: ninguna nueva. Biblioteca estándar (`json`, `csv`, `ipaddress`, `hmac`,
`hashlib`, `zoneinfo`, `unicodedata`, `random`) y Pydantic v2 (ya aprobado).

**Storage**: N/A (sin persistencia; llega en el incremento 2)

**Testing**: pytest (unitarias, sin servicios externos); fixtures en `tests/fixtures/ingestion/`

**Target Platform**: Linux (la misma imagen del incremento 0; `zoneinfo` verificado en `python:3.12-slim`)

**Project Type**: biblioteca dentro del proyecto único (`src/security_anomaly/`)

**Performance Goals**: 10.000 eventos ingeridos e informados en menos de 10 s (SC-001); dataset de
100.000 eventos sintéticos en menos de 60 s (SC-005); archivo excedido rechazado en menos de 1 s (SC-007)

**Constraints**: salida determinista byte a byte; ningún valor de entrada ni nombre de usuario en
informes ni logs; 10 MB por archivo, 10.000 eventos por lote, 256 caracteres por campo, rango de
fechas 2000-01-01 a 2100-01-01 (todo configurable)

**Scale/Scope**: ≈10 módulos fuente, ≈14 archivos de test, ≈20 fixtures

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Spec como fuente de verdad | Trazable a FR-001-01…30; sin dependencias ni endpoints nuevos; el único cambio fuera de la spec es un refactor menor de `core/config.py` (R11) | ✅ |
| II. Honestidad en la detección | No hay puntuación; los datos sintéticos se documentan como validación del software, no de detección | ✅ |
| III. Integridad del ML | Etiquetas de anomalías **separadas** de los eventos; generador con semilla fija; salida determinista; el generador no usa información futura | ✅ |
| IV. Seguridad y privacidad | Entrada no confiable (regex ancladas, límites, UTF-8 estricto); usuario seudonimizado con HMAC; identificadores del adaptador con HMAC (R6); informes y logs sin valores; clave solo por entorno | ✅ |
| V. Test-first | Tests antes del código en cada historia; tests de "no fuga" con cadenas centinela | ✅ |
| VI. Reproducibilidad | Semilla en el generador, catálogo versionado, sin estado entre lotes | ✅ |
| VII. Humano en el circuito / alcance mínimo | Sin endpoints, CLI, persistencia ni reentrenamiento | ✅ |

**Post-diseño:** sin cambios; sin violaciones, por lo que no hay entradas en Complexity Tracking.
**Hallazgo corregido durante el plan:** la spec contradecía a FR-001-04 al decir que un `outcome`
desconocido pasaba a `other`; FR-001-12 se acotó a `event_type` y `action`.

## Project Structure

### Documentation (this feature)

```text
specs/001-ingestion/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── ingestion-api.md          # API pública de la biblioteca y códigos de error
│   ├── event-v1.schema.json      # esquema JSON del evento de entrada v1
│   └── environment.md            # variables de entorno de la ingesta
├── checklists/requirements.md
└── tasks.md                      # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
src/security_anomaly/
├── core/config.py                # refactor: load_model() reutilizable (R11)
├── schemas/
│   ├── event.py                  # EventV1, NormalizedEvent, catálogo canónico
│   └── ingestion.py              # RejectionCode, Rejection, IngestionReport, IngestionResult
├── ingestion/
│   ├── __init__.py               # API pública
│   ├── errors.py                 # BatchRejected, PseudonymKeyMissing
│   ├── policy.py                 # IngestionPolicy (+ from_environ)
│   ├── pseudonym.py              # Pseudonymizer (HMAC)
│   ├── normalizer.py             # validación y normalización de un registro
│   ├── readers.py                # lectura JSON / JSON Lines / CSV con límites
│   ├── pipeline.py               # deduplicación, fuera de orden e informe
│   ├── adapters/
│   │   ├── __init__.py
│   │   └── linux_auth.py         # auth.log clásico → eventos v1
│   └── synthetic.py              # generador de eventos sintéticos + etiquetas
tests/
├── unit/ingestion/               # un archivo de test por módulo
├── unit/schemas/
└── fixtures/ingestion/           # JSON, CSV, auth.log y archivos inválidos
```

**Structure Decision:** se mantiene el proyecto único y los paquetes que fija la constitución; el
generador sintético vive en `ingestion/synthetic.py` (R10) y `schemas/` guarda los modelos de datos
compartidos con los incrementos posteriores.

## Fases de entrega (orden previsto para `/speckit-tasks`)

El orden vigente será el de `tasks.md`:

1. **Cimientos (Foundational):** refactor `load_model`, catálogo y modelos (`schemas/`), `IngestionPolicy`,
   errores, `Pseudonymizer`.
2. **US1 + US2 (P1):** normalizador, lectores JSON/CSV, pipeline (duplicados, informe) y rechazos con
   códigos y límites.
3. **US4 (P2):** normalización determinista completa, fuera de orden, categorías acotadas.
4. **US5 (P2):** seudonimización de extremo a extremo y tests de "no fuga".
5. **US3 (P2):** adaptador de `auth.log`.
6. **US6 (P3):** generador sintético y etiquetas.
7. **Cierre:** rendimiento, evidencia y revisión contra la spec.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Expresiones regulares vulnerables a entradas hostiles (ReDoS) en el adaptador | Anclaje, cuantificadores acotados, límite de 2.048 caracteres por línea y un test con entradas patológicas con tiempo máximo |
| Formatos reales de `auth.log` con variantes no previstas (por ejemplo, otras distribuciones) | Líneas no reconocidas se ignoran y cuentan aparte; fixtures con variantes de Debian/Ubuntu y RHEL, y revisión del recuento de ignoradas en datos reales |
| Cambio de año mal interpretado en archivos no cronológicos | Limitación documentada; test del caso diciembre → enero |
| Reproducibilidad del generador entre versiones de Python | Solo `random()` y aritmética propia; versión fijada por `uv.lock` y `requires-python` |
| Rotar `PSEUDONYM_KEY` rompe la idempotencia entre ingestas | Documentado en R6; la política de rotación se decide en el incremento 2 |
| Fixtures sintéticos mal interpretados como capacidad real de detección | Nota explícita en el model card futuro y en este documento (Principio II) |

## Complexity Tracking

Sin violaciones de la constitución; no aplica.
