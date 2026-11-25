# Research: Entrenamiento del modelo

Decisiones del incremento 4. Contexto: [spec.md](spec.md), SPEC §5 y §7, constitución (Principios III y VII).

## R1. Dependencia `scikit-learn` (ADR 0005)

- **Decisión:** añadir `scikit-learn` (con `numpy`, `scipy` y `joblib` como transitivas) con una cota inferior
  y superior de versión mayor, fijada por `uv.lock`. Se registra en `docs/decisions/0005-scikit-learn.md` antes
  de implementar. Sin `pandas`.
- **Racional:** SPEC §5.1 fija `IsolationForest` y `ColumnTransformer`. `joblib` es la serialización estándar de
  sus modelos.
- **Alternativas:** implementar el algoritmo a mano (más riesgo, contradice SPEC), usar `pandas` (dependencia
  grande sin necesidad: se trabaja con arrays).

## R2. Dataset y huella

- **Decisión:** `TrainingDataset` = tupla de `FeatureVector` ordenados por `(timestamp, source, event_id)` más
  la versión y la huella del esquema. Se construye con `features_for_range` (streaming). Se rechaza un vector con
  otra versión o huella de esquema. La huella del dataset es el SHA-256 de, por vector y en orden: `source`,
  `event_id`, `timestamp` ISO, versión de esquema y los valores de las características en el orden del esquema
  (flotantes con `float.hex()`, para exactitud). Solo se guarda el hash.
- **Racional:** identifica el dataset sin guardar identificadores y es sensible a cualquier cambio.
- **Alternativas:** hash del archivo de origen (no existe), hash de solo los identificadores (no ve cambios de
  valores).

## R3. Separación temporal

- **Decisión:** tres bloques contiguos: `n_train = floor(0.70 n)` y `n_cal = floor(0.15 n)` por defecto, el resto
  a prueba. Las fronteras se desplazan hacia adelante hasta el siguiente `timestamp` distinto para no partir un
  instante entre dos conjuntos (clarificado). Mínimo configurable por conjunto (por defecto 100); por debajo →
  `MlError("insufficient_data")`.
- **Racional:** SPEC §5.2 exige separación temporal; el desplazamiento mantiene a los empatados juntos.
- **Alternativas:** partición aleatoria (fuga temporal), fronteras exactas por índice (parten empates).

## R4. Transformaciones

- **Decisión:** `ColumnTransformer` sobre un array de objetos con una columna por característica del esquema:
  las 10 numéricas e indicadoras pasan por un `FunctionTransformer` que las convierte a `float64`; las 4
  categóricas (`event_type`, `action`, `outcome`, `source`) por `OneHotEncoder(handle_unknown="ignore",
  sparse_output=False)`. Se ajusta solo con el conjunto de entrenamiento. Las categorías se ordenan por nombre.
- **Racional:** cumple SPEC §5.1 sin `pandas`; una categoría desconocida da un vector de ceros en su bloque y no
  falla (FR-004-06). Usuario, IP, host e `event_id` no existen en el vector, así que no pueden codificarse
  (FR-004-07).
- **Alternativas:** `OrdinalEncoder` (introduce un orden arbitrario), escalar (no aporta a los árboles).

## R5. Modelo

- **Decisión:** `IsolationForest(n_estimators=100, max_samples="auto", random_state=42, n_jobs=1)`, sin
  `contamination` (se deja en su valor `"auto"`, que no filtra ni decide nada). Los parámetros son configurables.
- **Racional:** SPEC §5.1; `n_jobs=1` y la semilla dan resultados idénticos entre ejecuciones.
- **Alternativas:** fijar `contamination` (SPEC lo prohíbe), más hilos (no aporta determinismo adicional).

## R6. Calibración, severidad y bandera

- **Decisión:** `raw_score = -forest.score_samples(X)`. La distribución de calibración es el vector ordenado de
  `raw_score` del conjunto de calibración. `anomaly_score = bisect_right(calibration, raw) / len(calibration)`:
  fracción de puntuaciones de calibración menores o iguales, en [0, 1], monótona; 1 si supera a todas y 0 si es
  menor que todas. Severidad: `low` < `medium` ≤ score < `high`; `is_anomaly = score ≥ ANOMALY_THRESHOLD`. Umbrales
  validados: `0 < medium ≤ high ≤ 1` y `0 ≤ operativo ≤ 1`.
- **Racional:** SPEC §5.3; el percentil empírico no depende de la forma de la distribución.
- **Alternativas:** puntuación normalizada de `scikit-learn` (no es un percentil), probabilidad calibrada (SPEC
  lo prohíbe).

## R7. Evaluación

- **Decisión:** `evaluate(model, partition, labels=None, policy)` sobre el conjunto de prueba:
  - **Sin etiquetas:** cuantiles de `anomaly_score` (0, 0,5, 0,9, 0,95, 0,99 y 1) y su media, **estabilidad
    temporal** (la prueba se divide en 4 tramos consecutivos de igual tamaño; para cada uno la media de
    `anomaly_score` y la tasa de alertas, y la diferencia máxima entre tasas), **proporción de alertas** sobre el
    umbral operativo y recuento de contextos incompletos por conjunto.
  - **Con etiquetas** (`event_id → etiqueta`, positivo = cualquier etiqueta distinta de `normal`): precision,
    recall, F1 al umbral operativo, matriz de confusión y PR-AUC (`average_precision_score`); si no hay positivos
    o negativos, las métricas se marcan «no calculables».
  - **Limitaciones** como texto fijo: datos sintéticos, umbrales provisionales, no demuestra detección real, sin
    precisión mínima prometida.
- **Racional:** SPEC §5.4; las etiquetas solo entran aquí (FR-004-17, 18).
- **Alternativas:** ROC-AUC (engañosa con clases desbalanceadas), seleccionar umbral con las etiquetas de prueba
  (fuga).

## R8. Artefactos

- **Decisión:** un archivo por versión, `model-<version>.joblib`, dentro de `MODEL_DIR`. Contiene un
  `TrainedModel` (transformaciones, bosque, calibración, esquema y parámetros). Se guardan con `joblib` en un
  archivo temporal del mismo directorio y se renombran de forma atómica; el SHA-256 se calcula sobre el archivo
  final. Se registra también la versión de `scikit-learn`, `numpy` y `scipy`.
- **Carga segura:** el nombre se deriva de la versión registrada (nunca de la entrada), se resuelve la ruta real y
  debe quedar dentro de `MODEL_DIR`, ser un archivo regular y no un enlace que escape; se compara su huella con la
  registrada **antes** de abrirlo; se comprueba que las versiones de las librerías coinciden con las registradas.
- **Racional:** `joblib` usa `pickle`: deserializar un archivo manipulado ejecuta código. La verificación previa de
  la huella contra la base de datos convierte el riesgo en uno de integridad (FR-004-29).
- **Alternativas:** `skops` (dependencia nueva, no aprobada), ONNX (otra dependencia y no es el pipeline exacto).

## R9. Tablas y migración 0002

- **Decisión:** `training_runs` y `model_versions` (columnas en [data-model.md](data-model.md)) por una migración
  escrita a mano, con `CHECK` de estados, un **índice único parcial** que impide dos `running` y otro que impide
  dos `active`. Permisos al rol `anomaly_app`: `SELECT, INSERT` sobre ambas y `UPDATE` **solo por columna**
  (`status`, `heartbeat_at`, `finished_at`, `dataset_hash`, `version`, `error_code` y los recuentos en
  `training_runs`; `active` y `activated_at` en `model_versions`). Nadie recibe `DELETE`. `downgrade` protegido
  como el de 0001.
- **Racional:** la inmutabilidad de versiones y la concurrencia 1 pasan a ser garantías de la base de datos, no
  convenciones (FR-004-23, 26, 27).
- **Alternativas:** triggers (más código), permiso de tabla completo (no impide editar métricas).

## R10. Versionado

- **Decisión:** versión secuencial `v0001`, `v0002`…, asignada dentro de la transacción de registro como el
  máximo + 1 (segura porque solo puede haber un entrenamiento a la vez); `number` único.
- **Racional:** legible y ordenada; el hash del dataset y la fecha van en el registro.
- **Alternativas:** UUID (ilegible), fecha (dos modelos el mismo segundo).

## R11. Activación

- **Decisión:** `activate_version(engine, version, *, approved)`: sin `approved=True` →
  `MlError("approval_required")` antes de abrir la base de datos. Dentro de una transacción: candado de
  asesoramiento (`pg_advisory_xact_lock`), comprobar que la versión existe, `UPDATE … SET active = false WHERE
  active`, `UPDATE … SET active = true, activated_at = now() WHERE version = :v`. La verificación de integridad
  del artefacto se hace **antes** de activar (hash contra el archivo). Entrenar nunca activa.
- **Racional:** FR-004-26; el candado y el índice único garantizan una sola versión activa con activaciones
  simultáneas.
- **Alternativas:** una columna `active_version` en otra tabla (más estado).

## R12. Concurrencia 1 y proceso aparte

- **Decisión:** `begin_training_run` inserta un registro en estado `running`; el índice único parcial hace que un
  segundo intento falle y se traduzca en `MlError("training_in_progress")`. Un **latido** (`heartbeat_at`) se
  actualiza en cada fase; antes de lanzar, `mark_stale_runs_failed(max_age)` marca como `failed` (código
  `stale`) los `running` cuyo latido supera el límite (60 min por defecto). El proceso es la propia CLI: quien la
  lanza (una persona hoy, la API del incremento 5 mañana) lo hace en un proceso distinto.
- **Racional:** D7 sin Celery ni Redis; funciona aunque el proceso muera.
- **Alternativas:** un candado de archivo (no sirve entre contenedores), un servicio de colas (no aprobado).

## R13. CLI

- **Decisión:** `python -m security_anomaly.ml` con `train`, `status`, `list` y `activate` (solo `argparse`).
  Salida: una línea JSON; códigos de salida 0 (correcto), 2 (configuración o argumentos inválidos), 1 (error
  controlado, con su `code`). `activate` exige `--approve`. Las etiquetas opcionales se leen de un archivo JSON
  (`event_id → etiqueta`) de tamaño acotado, solo como datos (nunca `pickle`). Usa `DATABASE_URL` (rol de
  aplicación) y `MODEL_DIR`.
- **Racional:** Principio VII y D7 sin API; mismo patrón que la CLI del incremento 2.

## R14. Errores y registros

- **Decisión:** `MlError` con códigos estables (`insufficient_data`, `invalid_schema`, `invalid_parameters`,
  `training_in_progress`, `training_failed`, `unknown_version`, `approval_required`, `no_active_model`,
  `artifact_path`, `artifact_integrity`, `incompatible_environment`, `incompatible_features`) y mensajes fijos.
  Registros `training_started`, `training_finished` y `model_activated` con recuentos, duraciones, versiones y
  códigos.
- **Racional:** mismo patrón que `StorageError` y `FeatureError`; nunca valores de datos ni rutas internas.

## R15. Pruebas

- **Unitarias:** partición (bordes, empates, mínimos), huella, transformaciones (categorías desconocidas, sin
  identificadores), percentil y severidad (bordes), evaluación (con y sin etiquetas, sin positivos), artefactos
  (ruta, huella, versión de librerías), reproducibilidad (dos entrenamientos y procesos con `PYTHONHASHSEED`
  distintos), **fugas** (mutación de calibración y prueba no cambia transformaciones ni modelo), mismo pipeline
  (cargado = recién entrenado), centinelas de privacidad, rendimiento.
- **Integración (PostgreSQL real):** migración 0002 y permisos por columna, concurrencia 1 con hilos, activación con
  una sola versión activa con hilos, entrenamiento huérfano, flujo completo (ingesta sintética → características →
  entrenamiento → activación → carga → puntuación).
- **CI:** los jobs existentes bastan; `uv sync --frozen` instala la dependencia nueva.
