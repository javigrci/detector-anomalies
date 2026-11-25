# Data Model: Entrenamiento del modelo

Modelos en memoria (Pydantic v2, inmutables) en `schemas/ml.py` y dos tablas nuevas (migración `0002`).

## Tabla `training_runs`

| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| `id` | `UUID` | No | clave primaria |
| `status` | `TEXT` | No | `running`, `succeeded`, `failed` |
| `started_at` | `TIMESTAMPTZ` | No | `DEFAULT now()` |
| `heartbeat_at` | `TIMESTAMPTZ` | No | `DEFAULT now()`; se actualiza en cada fase |
| `finished_at` | `TIMESTAMPTZ` | Sí | fecha de fin |
| `params` | `JSONB` | No | parámetros del entrenamiento (sin valores de datos) |
| `dataset_hash` | `TEXT` | Sí | SHA-256 del dataset |
| `n_train`, `n_calibration`, `n_test` | `INTEGER` | Sí | tamaños de los conjuntos |
| `version` | `TEXT` | Sí | versión producida |
| `error_code` | `TEXT` | Sí | código de error sin valores |

Índice único parcial `uq_training_runs_one_running` sobre `(status) WHERE status = 'running'`: **a lo sumo un
entrenamiento en curso**.

## Tabla `model_versions`

| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| `version` | `TEXT` | No | clave primaria, `v0001`… |
| `number` | `INTEGER` | No | único; secuencia |
| `run_id` | `UUID` | No | entrenamiento que la produjo (`training_runs.id`) |
| `created_at` | `TIMESTAMPTZ` | No | `DEFAULT now()` |
| `schema_version` | `INTEGER` | No | versión del esquema de características |
| `schema_fingerprint` | `TEXT` | No | huella del esquema |
| `params` | `JSONB` | No | hiperparámetros y política de separación |
| `metrics` | `JSONB` | No | informe de evaluación |
| `dataset_hash` | `TEXT` | No | SHA-256 del dataset |
| `artifact_file` | `TEXT` | No | nombre del archivo (sin ruta) |
| `artifact_sha256` | `TEXT` | No | huella del archivo |
| `library_versions` | `JSONB` | No | versiones de scikit-learn, numpy y scipy |
| `active` | `BOOLEAN` | No | `DEFAULT false` |
| `activated_at` | `TIMESTAMPTZ` | Sí | cuándo se activó |

Índice único parcial `uq_model_versions_one_active` sobre `(active) WHERE active`: **a lo sumo una versión activa**.

### Privilegios del rol `anomaly_app`

| Tabla | Privilegios |
|---|---|
| `training_runs` | `SELECT`, `INSERT`, `UPDATE` solo en `status`, `heartbeat_at`, `finished_at`, `dataset_hash`, `n_train`, `n_calibration`, `n_test`, `version`, `error_code` |
| `model_versions` | `SELECT`, `INSERT`, `UPDATE` solo en `active`, `activated_at` |

Sin `DELETE` ni `TRUNCATE`; el rol de mantenimiento y el de migraciones no cambian (el migrador es el propietario).

## Modelos en memoria (`schemas/ml.py`)

### MlPolicy

| Campo | Por defecto | Regla |
|---|---|---|
| `train_fraction` | 0,70 | > 0 |
| `calibration_fraction` | 0,15 | > 0; `train + calibration < 1` |
| `min_events_per_set` | 100 | ≥ 1 |
| `n_estimators` | 100 | ≥ 1 |
| `max_samples` | `"auto"` | `"auto"` o entero ≥ 1 |
| `severity_medium` | 0,80 | `0 < medium ≤ high` |
| `severity_high` | 0,95 | `high ≤ 1` |
| `anomaly_threshold` | 0,80 | en [0, 1] |

### Score

`raw_score` (float), `anomaly_score` (float en [0, 1]), `severity` (`low`, `medium`, `high`), `is_anomaly` (bool).
Nunca se nombra probabilidad.

### EvaluationReport

`score_quantiles`, `score_mean`, `alert_rate`, `temporal_stability` (por tramo: media y tasa), `max_alert_rate_gap`,
`incomplete_context` (por conjunto), `labelled` (bool), `classification` (opcional: `precision`, `recall`, `f1`,
`pr_auc`, `confusion`, o «no calculables»), `limitations` (texto fijo).

### TrainedModel (artefacto)

Transformaciones ajustadas, `IsolationForest`, vector de calibración ordenado, versión y huella del esquema,
política y parámetros, y versiones de las librerías. Solo existe en memoria y en el archivo del artefacto.

### ModelVersion y TrainingRun

Reflejo de las filas de las tablas anteriores.

### MlError

`code ∈ {insufficient_data, invalid_schema, invalid_parameters, training_in_progress, training_failed,
unknown_version, unknown_run, approval_required, no_active_model, artifact_path, artifact_integrity,
incompatible_environment, incompatible_features}` y un mensaje fijo. Sin valores de datos, rutas ni credenciales.

## Estados

- **Entrenamiento:** `running` → `succeeded` | `failed`. Un `running` sin latido reciente pasa a `failed` (`stale`).
- **Versión:** registrada con `active = false` → `active = true` (por activación humana) → `active = false` (al
  activar otra). Nunca se borra ni se modifica otra columna.
