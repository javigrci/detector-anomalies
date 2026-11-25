# Implementation Plan: Entrenamiento del modelo

**Branch**: `004-model-training` | **Date**: 2026-11-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-model-training/spec.md`

## Summary

Biblioteca de entrenamiento del detector: dataset de vectores del incremento 3 con huella, separación temporal
70/15/15 sin solapes, transformaciones ajustadas solo con entrenamiento, Isolation Forest con semilla 42,
calibración por percentil con el conjunto de calibración, severidad configurable, evaluación con y sin etiquetas,
artefactos versionados en un directorio de confianza con huella SHA-256 verificada antes de cargar, registro de
entrenamientos y versiones en PostgreSQL (migración 0002 con permisos por columna), activación manual con
aprobación explícita y entrenamiento en proceso aparte con concurrencia 1 garantizada por la base de datos.
Incluye el ADR de `scikit-learn` y una línea de comandos mínima de operación. Sin endpoints ni dashboard.
Decisiones y alternativas en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: **nueva: `scikit-learn`** (con `numpy`, `scipy` y `joblib` como dependencias
transitivas), registrada en el ADR 0005. Resto: SQLAlchemy 2 (Core), Alembic, `psycopg` 3, Pydantic v2 y biblioteca
estándar. Se consume `security_anomaly.features` (incremento 3) y `security_anomaly.storage` (incremento 2). Sin
`pandas`.

**Storage**: PostgreSQL 16 (tablas `training_runs` y `model_versions`, migración `0002`); artefactos de modelo como
archivos en un directorio interno de confianza (`MODEL_DIR`).

**Testing**: pytest. Unitarias sin servicios con datos sintéticos del incremento 1; integración contra PostgreSQL
real (marcador `integration`) para registro, concurrencia, activación y el flujo completo.

**Target Platform**: Linux (contenedor), mismo entorno que los incrementos anteriores.

**Project Type**: biblioteca dentro del proyecto único, más una CLI mínima de operación.

**Performance Goals**: entrenar y evaluar 100.000 eventos en menos de 5 minutos (SC-004); puntuar un evento
individual en menos de 50 ms p95 (SC-005).

**Constraints**: reproducibilidad (semilla 42, `n_jobs=1`, archivo de bloqueo); sin fuga hacia el entrenamiento;
artefactos solo de `MODEL_DIR` y tras verificar su huella; errores y registros sin valores de datos; sin endpoints;
una sola versión activa; activación solo con aprobación explícita.

**Scale/Scope**: ≈11 módulos fuente nuevos, ≈35 archivos de test, 1 migración, 2 ADR (0005: scikit-learn; 0006: confianza de artefactos y concurrencia), hasta 100.000 eventos en las
pruebas de rendimiento.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Spec como fuente de verdad | Trazable a FR-004-01…32. Hay **componentes no pedidos expresamente**: una CLI mínima, variables de entorno nuevas y la dependencia `scikit-learn`; se justifican en Complexity Tracking y en el ADR 0005 y se señalan para revisión | ✅ (con revisión) |
| II. Honestidad en la detección | `anomaly_score` es un percentil, nunca probabilidad; el informe lleva limitaciones y no promete precisión; datos sintéticos | ✅ |
| III. Integridad del ML (NON-NEGOTIABLE) | Separación temporal contigua; transformaciones, modelo y calibración ajustados cada uno con su conjunto; `random_state=42`; esquema (versión y huella) y huella del dataset guardados con cada modelo; el mismo pipeline para entrenar y puntuar; `raw_score = -score_samples` | ✅ |
| IV. Seguridad y privacidad | Artefactos solo de `MODEL_DIR`, ruta y enlaces validados, huella verificada antes de deserializar; registros sin identificadores; consultas parametrizadas; permisos de BD por columna | ✅ |
| V. Test-first | Tests antes del código; los de fuga hacia el entrenamiento, reproducibilidad y carga segura son puertas de aceptación | ✅ |
| VI. Reproducibilidad | Migración Alembic; `uv.lock` con la dependencia nueva; ADR antes de implementar; medidas con hardware y volumen | ✅ |
| VII. Humano en el circuito | Entrenar y activar los lanza una persona; la activación exige aprobación explícita; no hay reentrenamiento ni activación automáticos | ✅ |

**Post-diseño:** sin violaciones; los componentes no pedidos figuran en Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/004-model-training/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── ml-api.md               # API pública de la biblioteca y sus errores
│   ├── operations.md           # tablas, migración, permisos y CLI
│   └── environment.md          # variables de entorno nuevas
├── checklists/requirements.md
└── tasks.md                    # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
src/security_anomaly/
├── schemas/
│   └── ml.py                   # TrainingPolicy, Score, EvaluationReport, ModelVersion, TrainingRun
└── ml/
    ├── __init__.py             # API pública
    ├── errors.py               # MlError (códigos fijos, sin valores)
    ├── config.py               # MlSettings (MODEL_DIR, umbrales) y carga desde el entorno
    ├── dataset.py              # dataset de vectores, huella y separación temporal
    ├── pipeline.py             # transformaciones + Isolation Forest + calibración (TrainedModel)
    ├── scoring.py              # puntuación bruta, percentil, severidad, bandera
    ├── evaluation.py           # informe de evaluación con y sin etiquetas
    ├── artifacts.py            # guardado y carga segura de artefactos
    ├── schema.py               # tablas training_runs y model_versions
    ├── registry.py             # entrenamientos, versiones, concurrencia y activación
    ├── service.py              # orquestación del entrenamiento
    ├── __main__.py             # CLI: train, status, list, activate
    └── (migración) ../storage/migrations/versions/0002_create_ml_tables.py
docs/decisions/0005-scikit-learn.md
.env.example · pyproject.toml · uv.lock
tests/
├── unit/ml/                    # dataset, partición, pipeline, calibración, severidad, evaluación, artefactos
└── integration/ml/             # registro, concurrencia, activación, flujo completo, privilegios
```

**Structure Decision:** se usa el paquete `ml` que ya fija la constitución y `schemas/ml.py` para los modelos de
datos que consumirá el incremento 5.

## Fases de entrega (orden previsto para `/speckit-tasks`)

1. **Cimientos:** ADR 0005 (dependencia) y ADR 0006 (diseño), errores, configuración, modelos Pydantic y ayudas de test.
2. **US2 (P1):** puntuación calibrada: percentil, severidad y bandera (funciones puras).
3. **US1 (P1):** dataset, huella, separación temporal, transformaciones, Isolation Forest y entrenamiento.
4. **US3 (P1):** evaluación con y sin etiquetas y limitaciones.
5. **US4 (P2):** migración 0002, artefactos, registro de entrenamientos y versiones.
6. **US5 (P2):** activación con aprobación explícita y una sola versión activa.
7. **US6 (P2):** proceso aparte, concurrencia 1, estado, entrenamientos huérfanos y CLI.
8. **US7 (P3):** carga segura e inferencia con el mismo pipeline.
9. **Cierre:** rendimiento, documentación, escaneo de fugas, evidencia y revisión.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Fuga de calibración o prueba hacia el ajuste | Tests por mutación de esos conjuntos; las transformaciones, el modelo y la calibración se ajustan con funciones que solo reciben su propio conjunto |
| Resultados no reproducibles entre ejecuciones o equipos | `random_state=42`, `n_jobs=1`, categorías ordenadas, huella del dataset y versiones de librerías registradas; test con procesos distintos |
| Deserializar un artefacto manipulado (`joblib` usa `pickle`) | Solo desde `MODEL_DIR`; ruta resuelta y validada; huella SHA-256 verificada antes de abrir el archivo; versiones de librerías comprobadas |
| Dos entrenamientos o activaciones simultáneos | Índices únicos parciales (un solo `running`, un solo `active`) y un candado de asesoramiento en la activación; tests con hilos |
| Entrenamiento huérfano que bloquea para siempre | Latido y marcado de entrenamientos caducados como fallidos antes de lanzar otro |
| Dependencia pesada nueva | ADR 0005; solo `scikit-learn` (y transitivas); verificación de que la imagen de Docker sigue construyendo |
| Métricas engañosas con datos sintéticos | El informe lleva limitaciones explícitas y nunca promete precisión; las etiquetas solo se usan sobre prueba |
| Modelo entrenado con un esquema de características distinto del de inferencia | Esquema (versión y huella) en el artefacto; puntuar con otra huella se rechaza |

## Complexity Tracking

| Elemento | Por qué hace falta | Alternativa más simple descartada porque |
|---|---|---|
| Dependencia `scikit-learn` (con numpy, scipy, joblib) | SPEC §5.1 fija Isolation Forest y `ColumnTransformer` de scikit-learn | Implementarlo a mano sería más código y riesgo y contradice SPEC |
| CLI mínima `python -m security_anomaly.ml` (`train`, `status`, `list`, `activate`) | Entrenar y activar los lanza una persona (Principio VII) y D7 pide un proceso aparte; sin API no hay otra forma | Sin CLI solo se podría llamar desde código |
| Variables de entorno nuevas (`MODEL_DIR`, umbrales, fracciones) | El directorio de confianza y los umbrales configurables los exige el spec (FR-004-14, FR-004-29) | Valores fijos en el código impedirían configurar |
| Permisos por columna sobre dos tablas para el rol de aplicación | Hacen la inmutabilidad de las versiones una garantía de la base de datos (FR-004-23) | Un permiso de tabla completo permitiría modificar métricas o huellas |
