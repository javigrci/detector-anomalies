# Contrato de entorno del entrenamiento

Se suman a las de los incrementos [0](../../000-base/contracts/environment.md),
[1](../../001-ingestion/contracts/environment.md) y [2](../../002-persistence/contracts/environment.md).

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `MODEL_DIR` | Sí (entrenar, activar, cargar) | — | Directorio interno de confianza de los artefactos; debe existir y ser absoluto |
| `SEVERITY_MEDIUM` | No | `0.80` | Umbral de `medium`; `0 < medium ≤ high` |
| `SEVERITY_HIGH` | No | `0.95` | Umbral de `high`; `high ≤ 1` |
| `ANOMALY_THRESHOLD` | No | `0.80` | Umbral operativo de `is_anomaly`, en [0, 1] |
| `TRAIN_FRACTION` | No | `0.70` | Fracción más antigua para entrenar |
| `CALIBRATION_FRACTION` | No | `0.15` | Fracción siguiente para calibrar; el resto es prueba |
| `MIN_EVENTS_PER_SET` | No | `100` | Mínimo de eventos por conjunto |
| `IFOREST_N_ESTIMATORS` | No | `100` | Número de árboles |
| `TRAINING_STALE_MINUTES` | No | `60` | Latido máximo antes de dar un entrenamiento `running` por caducado |

Reglas:

- Los valores vacíos se tratan como ausentes; los errores nombran la variable y nunca su valor.
- `MODEL_DIR` solo contiene artefactos propios; nunca se carga nada fuera de él.
- `.env.example` incluye todas; la API del incremento 5 recibirá `MODEL_DIR` solo en modo lectura.
