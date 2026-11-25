---

description: "Tareas del incremento 4 — Entrenamiento del modelo"
---

# Tasks: Entrenamiento del modelo

**Input**: Documentos de diseño en `/specs/004-model-training/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (`ml-api.md`, `operations.md`, `environment.md`), quickstart.md

**Tests**: OBLIGATORIOS (Constitución, Principio V). Cada historia y cada módulo compartido empiezan por sus tareas de test; se escriben y se confirma que FALLAN antes de implementar. Los resultados se registran tal como salen. Los tests de fuga hacia el entrenamiento, de reproducibilidad y de carga segura son las puertas de aceptación del incremento.

**Organization**: Tareas agrupadas por historia de usuario en el orden de entrega del plan: Cimientos → US2 → US1 → US3 → US4 → US5 → US6 → US7 → Cierre. Los módulos `pipeline.py`, `registry.py`, `service.py` y `__init__.py` crecen a lo largo de varias historias, así que esas tareas de implementación son secuenciales entre sí aunque las historias sean funcionalmente independientes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1…US7)
- Cada tarea cita requisitos (FR-004-xx) y rutas exactas

## Notas de ejecución

- Se trabaja en `main`; los commits y pushes (T060 y T061) requieren autorización explícita (Principio VII).
- **Dependencia nueva:** solo `scikit-learn` (con `numpy`, `scipy` y `joblib` como transitivas), registrada en el ADR 0005 **antes** de usarla (T002 y T003). Sin `pandas`, sin `hypothesis`, sin ninguna otra. Si surge la necesidad de otra, parar y pedir aprobación.
- **Componentes no pedidos expresamente** (justificados en Complexity Tracking del plan y señalados para revisión): la CLI mínima `python -m security_anomaly.ml`, las variables de entorno nuevas y los permisos por columna del rol de aplicación.
- Los datos de los tests son sintéticos (generador del incremento 1: IPs de rangos de documentación, usuarios `userNNN`, hosts `srv-demo-NN`); los seudónimos y claves de las pruebas se generan al vuelo. Las etiquetas salen del generador y solo se usan para evaluar.
- Los fixtures de fugas llevan **cadenas centinela** (`SENTINEL-USER-…`, `SENTINEL-HOST-…`, `SENTINEL-ID-…`) para comprobar que no aparecen en artefactos, registros, informes, errores ni registros de actividad.
- Al hacer pruebas de mutación sobre el código, borrar `__pycache__` o ejecutar con `PYTHONDONTWRITEBYTECODE=1` para que un archivo restaurado en el mismo segundo no conserve el bytecode mutado.
- Comandos de verificación por tarea: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`, y `uv run pytest -q -m "not integration"` o `-m integration` (PostgreSQL temporal de `docs/handoff.md` §8; `DATABASE_URL` es el administrador).

---

## Phase 1: Setup (infraestructura compartida)

**Purpose**: estructura de directorios de test.

- [X] T001 Crear `tests/unit/ml/__init__.py`, `tests/integration/ml/__init__.py` y `tests/integration/ml/conftest.py` (fixture automática que vacía `model_versions`, `training_runs` y `events` con el rol migrador entre tests; las tablas nuevas existen tras T039, así que la limpieza de esas dos se activa cuando existan); comprobar que Ruff y mypy siguen en verde

---

## Phase 2: Foundational (prerrequisitos bloqueantes)

**Purpose**: ADR y dependencia, errores, modelos, configuración y ayudas de test que necesitan todas las historias.

**⚠️ CRITICAL**: ninguna historia puede empezar hasta terminar esta fase.

- [X] T002 [P] Escribir `docs/decisions/0005-scikit-learn.md` (español, estado Aceptada): se aprueba `scikit-learn` con `numpy`, `scipy` y `joblib` transitivas por SPEC §5.1 (`IsolationForest`, `ColumnTransformer`), con la cota de versión elegida y fijada por `uv.lock`; sin `pandas`; alternativas descartadas (implementar a mano, `pandas`, `skops`, ONNX); riesgos (`joblib` usa `pickle`: mitigación en R8) y consecuencias (tamaño de la imagen, versiones registradas con cada modelo) (Constitución VI; AGENTS.md regla 3)
- [X] T003 Añadir la dependencia con `uv add scikit-learn` (actualiza `pyproject.toml` y `uv.lock`); añadir en `pyproject.toml` el `[[tool.mypy.overrides]]` de `sklearn.*` y `joblib.*` con `ignore_missing_imports`; comprobar que `uv sync --frozen` funciona, que Ruff y mypy siguen en verde y que los tests existentes pasan; registrar la versión instalada en el ADR (T002)
- [X] T004 [P] Escribir `docs/decisions/0006-confianza-de-artefactos-y-concurrencia.md` (español, estado Aceptada): modelo de confianza de los artefactos (directorio interno, nombre derivado de la versión registrada, SHA-256 contra la base de datos antes de deserializar, versiones de librerías), calibración por percentil empírico y separación temporal 70/15/15 con empates juntos, concurrencia 1 y una sola versión activa garantizadas por índices únicos parciales y candado de asesoramiento, inmutabilidad por permisos de columna, activación solo con aprobación explícita, y las cinco decisiones de la sesión de clarificación tomadas en modo automático; alternativas descartadas y consecuencias (Constitución VI; FR-004-21, 26, 27, 29)
- [X] T005 [P] Test en `tests/unit/ml/test_errors.py` (primero): `MlError` con los códigos de `data-model.md` (`insufficient_data`, `invalid_schema`, `invalid_parameters`, `training_in_progress`, `training_failed`, `unknown_version`, `approval_required`, `no_active_model`, `artifact_path`, `artifact_integrity`, `incompatible_environment`, `incompatible_features`), mensaje fijo por código, distinto entre códigos, sin valores de datos, rutas ni credenciales (centinelas) en `str`, `repr` ni `args`; confirmar que falla (FR-004-31)
- [X] T006 [P] Test en `tests/unit/schemas/test_ml_models.py` (primero): `MlPolicy` (valores por defecto 0,70, 0,15, 100, 100, `"auto"`, 0,80, 0,95, 0,80; fracciones positivas con suma menor que 1; `0 < medium ≤ high ≤ 1`; umbral operativo en [0, 1]; árboles ≥ 1; `max_samples` `"auto"` o entero ≥ 1), `Score` (sin ningún campo llamado probabilidad; `anomaly_score` en [0, 1]; severidad en `low`/`medium`/`high`), `EvaluationReport`, `ModelVersion` y `TrainingRun` inmutables; los errores de validación no repiten valores; confirmar que falla (FR-004-08, 14, 15)
- [X] T007 [P] Test en `tests/unit/ml/test_config.py` (primero): `MlSettings` lee `MODEL_DIR` (obligatorio, absoluto y existente) y las variables opcionales de `contracts/environment.md` con sus valores por defecto; vacío = ausente; los errores nombran la variable y nunca su valor; una política cargada del entorno se valida igual que una construida a mano; confirmar que falla (FR-004-14, 29)
- [X] T008 Ampliar `tests/unit/test_repo_hygiene.py` (test primero): `EXPECTED_VARS` incluye `MODEL_DIR`, `SEVERITY_MEDIUM`, `SEVERITY_HIGH`, `ANOMALY_THRESHOLD`, `TRAIN_FRACTION`, `CALIBRATION_FRACTION`, `MIN_EVENTS_PER_SET`, `IFOREST_N_ESTIMATORS` y `TRAINING_STALE_MINUTES`; confirmar que falla
- [X] T009 Crear `tests/ml_factory.py`: construye un dataset sintético reproducible con `generate_synthetic` (semilla, ráfagas inyectadas), lo ingiere con `ingest_records` y calcula sus vectores con `compute_features`; devuelve vectores ordenados, las etiquetas del generador como mapa `event_id → etiqueta` y ayudas para partir en conjuntos y para resumir un modelo entrenado (resumen determinista de los parámetros del bosque, de las categorías y de la calibración) sin usar el código de producción de la partición; con tests mínimos en `tests/unit/ml/test_ml_factory.py` (reproducible, con ráfagas etiquetadas) (research R15)
- [X] T010 [P] Implementar `src/security_anomaly/ml/errors.py` (`MlError`); T005 pasa (T005)
- [X] T011 [P] Implementar `src/security_anomaly/schemas/ml.py` (`MlPolicy`, `Score`, `EvaluationReport`, `ModelVersion`, `TrainingRun`); T006 pasa (T006)
- [X] T012 Implementar `src/security_anomaly/ml/config.py` (`MlSettings`, carga desde el entorno con `load_model`); T007 pasa (T007, T011)
- [X] T013 Añadir a `.env.example` las variables de T008 con sus valores por defecto (`MODEL_DIR` con una ruta de ejemplo absoluta y comentada como interna de confianza); T008 pasa (T008)

**Checkpoint**: ADR y dependencia, errores, modelos, configuración y ayudas de test listos; las historias pueden empezar.

---

## Phase 3: User Story 2 - Puntuar de forma calibrada e interpretable (Priority: P1)

**Goal**: puntuación bruta, percentil de calibración en [0, 1], severidad y bandera de anomalía; nunca una probabilidad.

**Independent Test**: con una distribución de calibración conocida, comprobar el percentil por debajo, dentro y por encima del rango, y la severidad en los bordes de los umbrales.

### Tests for User Story 2 (MANDATORY) ⚠️

> Escribirlos primero y confirmar que FALLAN antes de implementar.

- [X] T014 [P] [US2] Test en `tests/unit/ml/test_percentile.py`: el percentil es la fracción de puntuaciones de calibración menores o iguales; 1 si supera a todas y 0 si es menor que todas; es monótono; maneja valores repetidos y una calibración con todas las puntuaciones iguales; la bruta es `-score_samples` (mayor valor, más anómalo) comprobado contra un bosque pequeño ajustado en el test; vectores vacíos dan listas vacías (FR-004-11, 12)
- [X] T015 [P] [US2] Test en `tests/unit/ml/test_severity.py`: con los umbrales por defecto, 0,79 → `low`, 0,80 → `medium`, 0,94 → `medium`, 0,95 → `high`, 1,0 → `high`, 0,0 → `low`; umbrales configurados se aplican; `is_anomaly` es verdadero desde el umbral operativo incluido; umbrales incoherentes (`high < medium`, fuera de [0, 1]) se rechazan con `MlError("invalid_parameters")` sin valores en el mensaje (FR-004-14, 15)
- [X] T016 [P] [US2] Test en `tests/unit/ml/test_no_probability_wording.py`: ningún campo, atributo ni nombre del paquete `security_anomaly.ml` ni de `schemas/ml.py` contiene `probabilidad` o `probability`; en sus docstrings, comentarios y mensajes, toda aparición de la palabra está en una frase que la niega (contiene «no es», «nunca», «not» o «never»); ídem en `specs/004-model-training/contracts/` y en la sección del README sobre el modelo cuando exista (SC-009; FR-004-16)

### Implementation for User Story 2

- [X] T017 [US2] Implementar `src/security_anomaly/ml/scoring.py`: `raw_scores`, `percentile`, `severity_of` e `is_anomaly_of` como funciones puras con validación de umbrales; T014–T016 pasan (T014–T016, T010, T011)

**Checkpoint**: US2 funcional y comprobable de forma independiente.

---

## Phase 4: User Story 1 - Entrenar un modelo reproducible con datos históricos (Priority: P1) 🎯 MVP

**Goal**: dataset con huella, separación temporal, transformaciones y modelo ajustados solo con entrenamiento, calibración con su conjunto y resultados idénticos entre ejecuciones.

**Independent Test**: entrenar dos veces con el mismo dataset sintético y comparar puntuaciones; alterar calibración y prueba y comprobar que transformaciones y modelo no cambian.

### Tests for User Story 1 (MANDATORY) ⚠️

- [X] T018 [P] [US1] Test en `tests/unit/ml/test_dataset_fingerprint.py`: la huella es un SHA-256 hexadecimal determinista, igual para el mismo dataset en procesos distintos, distinta con un solo valor, un solo identificador, el orden o la versión de esquema distintos; no depende del orden de construcción del dataset (se ordena antes); el hash no contiene identificadores (FR-004-05)
- [X] T019 [P] [US1] Test en `tests/unit/ml/test_split_temporal.py`: tres bloques contiguos y ordenados (entrenamiento el más antiguo, prueba el más reciente) que cubren todo el dataset sin solaparse; proporciones 70/15/15 con tolerancia de un instante; fracciones configurables; los empates de instante en una frontera se mueven juntos al siguiente conjunto; un dataset por debajo del mínimo por conjunto lanza `MlError("insufficient_data")` indicando el mínimo (sin valores de datos) y no entrena; un dataset con todos los eventos en el mismo instante se rechaza con claridad (FR-004-02…04)
- [X] T020 [P] [US1] Test en `tests/unit/ml/test_dataset_schema.py`: vectores con otra `schema_version`, otra huella de esquema o características que no coinciden con el esquema esperado lanzan `MlError("invalid_schema")` sin valores; un dataset vacío se rechaza; el dataset exige que todos los vectores compartan esquema (FR-004-01)
- [X] T021 [P] [US1] Test de integración en `tests/integration/ml/test_build_dataset.py`: con eventos guardados con `save_events`, `build_dataset` devuelve los mismos vectores que `compute_features` en memoria para el mismo rango, ordenados, con el esquema v1; un rango vacío da un dataset vacío (FR-004-01)
- [X] T022 [P] [US1] Test en `tests/unit/ml/test_transformations.py`: la matriz de características tiene una columna por numérica e indicadora y un bloque one-hot por categórica; las categorías se ajustan solo con entrenamiento y se ordenan por nombre; una categoría desconocida (por ejemplo una fuente nueva) da ceros en su bloque sin error y sin activar una columna conocida; ninguna columna procede de usuario, IP, host ni `event_id`; los valores numéricos son `float64`; el ajuste con un dataset sin categorías distintas no falla (FR-004-06, 07)
- [X] T023 [P] [US1] Test en `tests/unit/ml/test_reproducibility.py`: dos entrenamientos con el mismo dataset y parámetros dan puntuaciones brutas idénticas en el 100 % de un conjunto fijo y el mismo resumen del modelo; el mismo entrenamiento en procesos con `PYTHONHASHSEED` 0, 1, 4242 y aleatorio da el mismo resumen y las mismas puntuaciones; con otra semilla de datos el resultado cambia (control negativo) (SC-001; FR-004-09)
- [X] T024 [P] [US1] Test en `tests/unit/ml/test_no_leak_into_training.py` (**puerta de aceptación**): con ≥ 10 semillas, modificar, añadir y quitar eventos de los conjuntos de calibración y de prueba (valores, identificadores, número de eventos) no cambia las categorías ajustadas, los parámetros del bosque ni su resumen; modificar el conjunto de entrenamiento sí los cambia (control); el conjunto de prueba tampoco cambia la calibración (SC-002; FR-004-10, 13)
- [X] T025 [P] [US1] Test en `tests/unit/ml/test_model_parameters.py`: el bosque se entrena con `random_state` 42, sin `contamination` explícito y con `n_jobs` 1; `n_estimators` y `max_samples` configurables llegan al bosque; parámetros inválidos (árboles < 1, `max_samples` negativo) lanzan `MlError("invalid_parameters")` antes de entrenar; la calibración sale solo del conjunto de calibración (cambiar la calibración cambia su vector, cambiar el entrenamiento no lo hace sin cambiar el modelo) (FR-004-08, 13)

### Implementation for User Story 1

- [X] T026 [US1] Implementar `src/security_anomaly/ml/dataset.py`: `TrainingDataset`, `build_dataset` (con `features_for_range`), `dataset_fingerprint` y `split_temporal` con desplazamiento de fronteras por empates y mínimos por conjunto; T018–T021 pasan (T018–T021, T011, T017)
- [X] T027 [US1] Implementar `src/security_anomaly/ml/pipeline.py`: matriz de características con `ColumnTransformer` (numéricas por `FunctionTransformer` a `float64`, categóricas por `OneHotEncoder(handle_unknown="ignore", sparse_output=False)`), `IsolationForest(random_state=42, n_jobs=1)` y `train_model` que ajusta transformaciones y bosque solo con entrenamiento y la calibración solo con calibración; `score_vectors` y `score_vector`; `TrainedModel`; T022–T025 pasan (T022–T025, T026, T017)

**Checkpoint**: US1 y US2 funcionan de forma independiente; el modelo es reproducible y sin fugas.

---

## Phase 5: User Story 3 - Evaluar el modelo y documentar sus límites (Priority: P1)

**Goal**: informe con y sin etiquetas, estabilidad temporal, proporción de alertas y limitaciones, sin prometer precisión.

**Independent Test**: evaluar un dataset sintético con ráfagas etiquetadas y sin etiquetas.

### Tests for User Story 3 (MANDATORY) ⚠️

- [X] T028 [P] [US3] Test en `tests/unit/ml/test_evaluation_unlabelled.py`: sin etiquetas el informe contiene los cuantiles y la media de `anomaly_score`, la estabilidad temporal (4 tramos consecutivos con media y tasa de alertas, y la diferencia máxima), la proporción de alertas sobre el umbral operativo y el número de vectores con contexto incompleto de cada conjunto, y **no** contiene métricas de clasificación (FR-004-17, 20)
- [X] T029 [P] [US3] Test en `tests/unit/ml/test_evaluation_labelled.py`: con etiquetas, precision, recall, F1 y matriz de confusión coinciden con un caso pequeño calculado a mano y el PR-AUC con el de scikit-learn; solo se usan las etiquetas del conjunto de prueba; evaluar con y sin etiquetas deja el modelo y la calibración exactamente iguales; sin positivos o sin negativos las métricas se marcan «no calculables» sin dividir por cero; una etiqueta de un evento que no está en la prueba se ignora (FR-004-17, 18)
- [X] T030 [P] [US3] Test en `tests/unit/ml/test_evaluation_limitations.py`: el informe incluye el apartado de limitaciones (datos sintéticos, umbrales provisionales, no demuestra detección real) y ninguna frase que prometa una precisión mínima; su texto se serializa y no contiene valores de eventos (FR-004-19)
- [X] T031 [P] [US3] Test en `tests/unit/ml/test_burst_detection.py`: con un dataset sintético con ráfagas de fallos inyectadas (semillas fijas) y sus etiquetas, la puntuación de anomalía media de los eventos de ráfaga de la prueba es mayor que la del tráfico normal y la mayoría de los eventos de ráfaga supera el umbral operativo (SC-003; SPEC §2)

### Implementation for User Story 3

- [X] T032 [US3] Implementar `src/security_anomaly/ml/evaluation.py`: `evaluate` y el informe con y sin etiquetas, estabilidad temporal, proporción de alertas, contextos incompletos y limitaciones fijas; T028–T031 pasan (T028–T031, T027, T017)

**Checkpoint**: US1, US2 y US3 funcionan; el modelo se puede entrenar, puntuar y evaluar en memoria.

---

## Phase 6: User Story 4 - Versionar y registrar cada modelo (Priority: P2)

**Goal**: artefactos versionados en un directorio de confianza y registros de entrenamientos y versiones en PostgreSQL con permisos por columna.

**Independent Test**: entrenar y comprobar artefacto, versión y registros; entrenar de nuevo y comprobar que la huella del dataset coincide.

### Tests for User Story 4 (MANDATORY) ⚠️

- [X] T033 [P] [US4] Test de integración en `tests/integration/ml/test_migration_ml.py` y actualización de `tests/integration/test_alembic.py` (primero): `alembic upgrade head` crea `training_runs` y `model_versions` con sus columnas, `CHECK` de estado, índices únicos parciales (un solo `running`, una sola `active`) y clave foránea; aplicarla dos veces no cambia nada; `downgrade` se niega con filas salvo `-x destructive=yes`; los tests de la migración 0001 esperan ahora las tablas nuevas y siguen pasando (FR-004-24)
- [X] T034 [P] [US4] Test de integración en `tests/integration/ml/test_privileges_ml.py`: el rol de aplicación puede `SELECT`, `INSERT` y `UPDATE` solo las columnas permitidas de `training_runs` y de `model_versions` (`active`, `activated_at`) y se le deniega (SQLSTATE 42501) `UPDATE` de `metrics`, `params`, `artifact_sha256`, `dataset_hash`, `schema_fingerprint`, `DELETE`, `TRUNCATE` y DDL; el rol de mantenimiento no puede leer ni escribir esas tablas; el migrador sí; el estado real de la base de datos no cambia tras cada intento denegado (FR-004-23, 24)
- [X] T035 [P] [US4] Test en `tests/unit/ml/test_artifacts.py`: guardar escribe `model-<version>.joblib` en `MODEL_DIR` con un archivo temporal y renombrado atómico (sin temporales sobrantes), devuelve la huella SHA-256 del archivo final y las versiones de scikit-learn, numpy y scipy; el nombre se deriva de la versión con un patrón estricto y nunca contiene componentes de ruta; la resolución de la ruta rechaza `..`, rutas absolutas externas, un enlace simbólico que escapa de `MODEL_DIR`, un directorio o un archivo no regular, con `MlError("artifact_path")` sin rutas en el mensaje (FR-004-21, 29)
- [X] T036 [P] [US4] Test de integración en `tests/integration/ml/test_registry.py`: `run_training` con un dataset sintético guardado deja un `training_run` `succeeded`, una versión `v0001` con versión y huella del esquema, parámetros, métricas, fecha, huella del dataset, huella del artefacto y versiones de librerías, y el archivo en `MODEL_DIR`; la huella del dataset coincide en un segundo entrenamiento y la versión es `v0002` sin modificar `v0001`; ningún entrenamiento activa su versión; un fallo forzado (por ejemplo, fallo al registrar) deja el entrenamiento en `failed` con `error_code`, sin versión y sin archivo huérfano (FR-004-21…23, 25, 26)
- [X] T037 [P] [US4] Test en `tests/integration/ml/test_no_identifiers_stored.py`: con IP, seudónimo, host e identificador centinela en los eventos, ninguno aparece en los bytes del artefacto, ni en `params`, `metrics` ni `dataset_hash` de los registros, ni en el informe de evaluación serializado (FR-004-23; SC-008)

### Implementation for User Story 4

- [X] T038 [US4] Escribir `src/security_anomaly/storage/migrations/versions/0002_create_ml_tables.py` a mano (tablas, `CHECK`, índices únicos parciales, clave foránea, `GRANT` por columna a `anomaly_app`, `downgrade` protegido) e implementar `src/security_anomaly/ml/schema.py` con las dos `Table` en el mismo `MetaData` de `storage/schema.py`; T033 y T034 pasan (T033, T034)
- [X] T039 [US4] Implementar `src/security_anomaly/ml/artifacts.py` (guardado atómico, huella, resolución segura de la ruta, versiones de librerías); T035 pasa (T035, T010)
- [X] T040 [US4] Implementar en `src/security_anomaly/ml/registry.py`: registro de entrenamientos, registro de versiones (`v0001`… asignada dentro de la transacción), consultas `get_training_run`, `list_versions` y `get_version`, con errores traducidos a `MlError`/`StorageError` y registros `training_started`/`training_finished` solo con recuentos, duraciones, versiones y códigos; T036 parcial pasa (T036, T038, T039)
- [X] T041 [US4] Implementar `src/security_anomaly/ml/service.py` (`run_training`): marca el entrenamiento, construye dataset, separa, entrena, evalúa, guarda el artefacto, registra la versión y deja el entrenamiento en `succeeded`; ante cualquier fallo lo deja en `failed` con su código y elimina el artefacto si lo hubo; **no activa**; T036 y T037 pasan (T036, T037, T040, T026, T027, T032)

**Checkpoint**: US1 a US4 funcionan; cada modelo queda versionado y registrado.

---

## Phase 7: User Story 5 - Activar una versión solo con autorización humana (Priority: P2)

**Goal**: una sola versión activa, con aprobación explícita y sin activaciones automáticas.

**Independent Test**: registrar dos versiones, activar una con y sin aprobación y comprobar el estado.

### Tests for User Story 5 (MANDATORY) ⚠️

- [X] T042 [P] [US5] Test de integración en `tests/integration/ml/test_activation.py`: activar con aprobación deja esa versión como única activa y anota `activated_at`; activar otra desactiva la anterior; con 8 hilos activando versiones distintas a la vez nunca hay más de una activa (SC-007); una versión inexistente da `MlError("unknown_version")`; un artefacto manipulado o ausente se rechaza antes de activar con `MlError("artifact_integrity")` y no cambia nada; entrenar no activa y no hay reentrenamiento ni activación sin una llamada explícita (FR-004-26)
- [X] T043 [P] [US5] Test en `tests/unit/ml/test_activation_approval.py`: `activate_version(..., approved=False)` y la ausencia de aprobación lanzan `MlError("approval_required")` **sin abrir la base de datos** (motor simulado que falla si se usa) y sin valores en el mensaje (FR-004-26)

### Implementation for User Story 5

- [X] T044 [US5] Implementar `activate_version` y `get_active_version` en `src/security_anomaly/ml/registry.py`: aprobación comprobada antes de todo, verificación de integridad del artefacto, una transacción con candado de asesoramiento que desactiva la activa y activa la elegida; registro `model_activated` solo con la versión y la duración; T042 y T043 pasan (T042, T043, T040, T039)

**Checkpoint**: US1 a US5 funcionan.

---

## Phase 8: User Story 6 - Entrenar como proceso aparte, uno a la vez, y consultar su estado (Priority: P2)

**Goal**: concurrencia 1 garantizada por la base de datos, estado consultable, entrenamientos huérfanos recuperables y CLI de operación.

**Independent Test**: lanzar un entrenamiento, intentar otro mientras corre y consultar el estado.

### Tests for User Story 6 (MANDATORY) ⚠️

- [X] T045 [P] [US6] Test de integración en `tests/integration/ml/test_training_concurrency.py`: dos hilos que abren un entrenamiento a la vez producen exactamente un `running` y un `MlError("training_in_progress")`; con 8 hilos, como máximo uno (SC-007); `get_training_run` refleja `running` y luego `succeeded` o `failed`; un `running` con latido anterior al límite se marca `failed` con `error_code` `stale` y permite lanzar otro; un latido reciente no se marca; el latido se actualiza en cada fase (FR-004-27)
- [X] T046 [P] [US6] Test en `tests/unit/ml/test_cli.py`: subcomandos `train`, `status`, `list` y `activate` con `argparse`; salida de **una línea JSON** con recuentos, estados, versiones y códigos; códigos de salida 0, 1 (solo el `code` de `MlError`/`StorageError`) y 2 (configuración o argumentos inválidos, nombrando la variable y no su valor); `activate` sin `--approve` sale con error y no llama a la biblioteca; `--history-start` toma por defecto el valor de `--start`; `--labels` lee solo JSON de tamaño acotado (un archivo mayor o que no es JSON se rechaza sin ejecutar nada); nunca imprime credenciales, rutas ni valores (centinelas) (FR-004-28, 31)
- [X] T047 [P] [US6] Test de integración en `tests/integration/ml/test_cli_end_to_end.py`: con `DATABASE_URL` del rol de aplicación y un `MODEL_DIR` temporal, un **proceso aparte** (`subprocess`) ejecuta `train`, después `list`, `activate --approve` y `status`; la segunda orden de `train` lanzada mientras la primera corre se rechaza con `training_in_progress`; la salida de cada orden es una línea JSON parseable; el servicio y las demás conexiones no se bloquean mientras entrena (FR-004-27, 28)

### Implementation for User Story 6

- [X] T048 [US6] Implementar en `registry.py` y `service.py` la apertura del entrenamiento con el índice único (traducción a `training_in_progress`), el latido por fase y `mark_stale_runs_failed(max_age)` que `run_training` ejecuta antes de abrir uno nuevo; T045 pasa (T045, T040, T041)
- [X] T049 [US6] Implementar la CLI en `src/security_anomaly/ml/__main__.py` (solo `argparse`): `train`, `status`, `list` y `activate --approve`, con `MlSettings`, `DATABASE_URL` y las políticas del entorno; T046 y T047 pasan (T046, T047, T044, T048, T012)

**Checkpoint**: US1 a US6 funcionan.

---

## Phase 9: User Story 7 - Cargar modelos solo de ubicaciones de confianza y reutilizarlos para puntuar (Priority: P3)

**Goal**: carga segura con huella verificada y el mismo pipeline para entrenar y puntuar.

**Independent Test**: guardar y cargar un modelo y comparar las puntuaciones; manipular el artefacto o pedir una ruta externa.

### Tests for User Story 7 (MANDATORY) ⚠️

- [X] T050 [P] [US7] Test de integración en `tests/integration/ml/test_load_model.py`: un modelo cargado puntúa idéntico al recién entrenado en el 100 % de un conjunto de eventos (FR-004-30); un byte modificado en el artefacto lanza `MlError("artifact_integrity")` y `joblib.load` **no se llega a llamar** (comprobado con un doble); un nombre con componentes de ruta, una ruta fuera de `MODEL_DIR` y un enlace simbólico que escapa se rechazan con `MlError("artifact_path")` antes de abrir nada (SC-006); un archivo ausente da un error controlado; versiones de scikit-learn, numpy o scipy distintas de las registradas lanzan `MlError("incompatible_environment")`; puntuar un vector con otra versión o huella de esquema lanza `MlError("incompatible_features")`; `load_active_model` sin versión activa lanza `MlError("no_active_model")`; ninguna ruta, valor ni credencial en los mensajes (FR-004-29, 30)
- [X] T051 [P] [US7] Test en `tests/unit/ml/test_public_api_contract.py`: las firmas y los nombres exportados por `security_anomaly.ml` (`build_dataset`, `dataset_fingerprint`, `split_temporal`, `train_model`, `score_vectors`, `score_vector`, `evaluate`, `run_training`, `activate_version`, `get_active_version`, `get_training_run`, `list_versions`, `load_model`, `load_active_model`, `MlError`, `MlPolicy`, `MlSettings`, `TrainedModel`, `Score`) coinciden con `contracts/ml-api.md`

### Implementation for User Story 7

- [X] T052 [US7] Implementar `load_model` y `load_active_model` en `src/security_anomaly/ml/artifacts.py` y `registry.py` (resolución segura de la ruta a partir del nombre registrado, huella verificada **antes** de abrir, versiones de librerías, comprobación del esquema al puntuar) y exportar la API en `src/security_anomaly/ml/__init__.py`; T050 y T051 pasan (T050, T051, T039, T044)

**Checkpoint**: las siete historias funcionan.

---

## Phase 10: Polish y cierre

**Purpose**: rendimiento, escaneo de fugas, documentación, imagen de Docker, evidencia y revisión.

- [X] T053 [P] Test de rendimiento en `tests/unit/ml/test_perf_training.py`: entrenar y evaluar 100.000 eventos sintéticos en menos de 5 minutos y puntuar un evento individual (carga ya hecha) en menos de 50 ms en el percentil 95 sobre ≥ 200 mediciones; los umbrales son los del SC y solo se ajustan con una justificación registrada; se imprimen el tiempo real, el volumen, el hardware y las condiciones (Constitución VI) (SC-004, SC-005)
- [X] T054 [P] Test transversal en `tests/integration/ml/test_no_leaks_ml.py`: con usuarios, IPs, hosts, identificadores y rutas centinela, recorrer entrenamiento, evaluación, registro, activación, carga, CLI y errores, y comprobar que ningún valor aparece en artefactos, registros de la base de datos, informes, errores, salida de la CLI ni registros de actividad (SC-008; FR-004-31)
- [X] T055 [P] Documentar en `README.md` el entrenamiento (qué hace, la separación temporal, la calibración, la evaluación y sus límites, el directorio de modelos, la CLI y la activación manual; recalcar que `anomaly_score` no es una probabilidad de ataque y que los datos de prueba son sintéticos), y añadir a `docs/data-contract.md` la sección «Modelo y versiones»; actualizar `docs/handoff.md` y `docs/roadmap.md`
- [X] T056 Comprobar que la imagen de Docker sigue construyendo con la dependencia nueva (`docker build .`), que `uv sync --frozen` funciona en limpio y que la CI no necesita cambios (el job `integration` aplica ya la migración 0002); registrar el tamaño de la imagen antes y después (ADR 0005)
- [X] T057 Ejecutar la calidad completa: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`, `uv run pytest -q -m "not integration"` y `uv run pytest -q -m integration` contra PostgreSQL temporal; registrar los resultados reales sin editarlos; si algo falla, el incremento no está cerrado (AGENTS.md reglas 6 y 8) (T053–T056)
- [X] T058 Ejecutar el `quickstart.md` completo (escenarios 1 a 10) y escribir `specs/004-model-training/verification.md` con resultados reales, tiempos medidos (SC-004, SC-005) junto con hardware, volumen y condiciones, matriz FR/SC → test, riesgos, decisiones tomadas en modo automático y decisiones pendientes; comprobar con mutaciones que los tests detectan: ajustar las transformaciones con todo el dataset, calibrar con el conjunto de prueba, cargar sin verificar la huella y permitir dos versiones activas; marcar `[X]` solo lo comprobado (T057)
- [X] T059 Confirmar que el único cambio de dependencias es `scikit-learn` (y sus transitivas en `uv.lock`), ni endpoints, ni API, ni dashboard, ni secretos en el diff, ni `.env` (FR-004-32; AGENTS.md regla 3) (T057)
- [ ] T060 **Requiere autorización explícita:** commit en `main` con el mensaje de cierre en español y la línea `Co-Authored-By` fijada por el entorno (T058, T059)
- [ ] T061 **Requiere autorización explícita:** `git push` y comprobar que los tres jobs de la CI quedan en verde, anotando el identificador del run en `verification.md` (T060)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sin dependencias.
- **Foundational (Fase 2)**: depende de Setup; **bloquea** todas las historias. T002 y T003 (ADR y dependencia) van antes que cualquier código que importe `sklearn`.
- **Historias (Fases 3 a 9)**: dependen de Foundational. Orden de entrega: US2 → US1 → US3 → US4 → US5 → US6 → US7.
- **Cierre (Fase 10)**: depende de las historias.

### Dependencias entre historias

- **US2** (percentil, severidad): funciones puras, sin dependencias de otras historias.
- **US1** (dataset y entrenamiento): usa el percentil de US2 para la calibración.
- **US3** (evaluación): depende de US1 y US2.
- **US4** (registro y artefactos): depende de US1 y US3 (`run_training` entrena y evalúa).
- **US5** (activación): depende de US4.
- **US6** (concurrencia y CLI): depende de US4 y US5.
- **US7** (carga segura): depende de US4 y US5; su API pública agrupa las anteriores.

### Dentro de cada historia

- Tests primero y confirmados en rojo; luego implementación, registros y API pública.
- Después de cada tarea: Ruff, mypy y los tests afectados.

### Parallel Opportunities

- T005–T007 y T010–T011 (archivos distintos); T002 en paralelo con todo lo que no importe `sklearn`.
- Todos los tests de una historia marcados [P].
- Los tests de US5, US6 y US7 pueden prepararse en paralelo con la implementación de US4, salvo los archivos compartidos (`registry.py`, `service.py`, `__init__.py`).
- T053 a T055 en el cierre.

## Parallel Example: User Story 1

```bash
# Tests de US1 juntos:
Task: "Test en tests/unit/ml/test_dataset_fingerprint.py"
Task: "Test en tests/unit/ml/test_split_temporal.py"
Task: "Test en tests/unit/ml/test_transformations.py"
Task: "Test en tests/unit/ml/test_reproducibility.py"
Task: "Test en tests/unit/ml/test_no_leak_into_training.py"
```

## Implementation Strategy

### MVP primero (US2 + US1)

1. Fase 1 y Fase 2 (cimientos, ADR y dependencia).
2. Fase 3 (US2) y Fase 4 (US1): un modelo reproducible, sin fugas y calibrado en memoria.
3. **PARAR y validar** con los escenarios 2 a 4 de `quickstart.md`; es la puerta de aceptación del roadmap (modelo reproducible).

### Entrega incremental

1. Cimientos → US2 → US1 → US3 (entrenar, puntuar y evaluar).
2. US4 y US5 (registro, versiones y activación manual) antes de que exista ninguna API.
3. US6 (proceso aparte y CLI), US7 (carga segura) y cierre con `verification.md`.

## Cobertura de requisitos

| Requisito | Tareas |
|---|---|
| FR-004-01 | T020, T021, T026 |
| FR-004-02…04 | T019, T026 |
| FR-004-05 | T018, T026 |
| FR-004-06, 07 | T022, T027 |
| FR-004-08, 09 | T006, T023, T025, T027 |
| FR-004-10, 13 | T024, T025, T027 |
| FR-004-11, 12 | T014, T017, T027 |
| FR-004-14, 15 | T006, T007, T015, T017 |
| FR-004-16 | T016 |
| FR-004-17…20 | T028–T032 |
| FR-004-21…23, 25 | T035–T037, T039–T041 |
| FR-004-24 | T033, T034, T038 |
| FR-004-26 | T036, T042–T044 |
| FR-004-27, 28 | T045–T049 |
| FR-004-29, 30 | T035, T050, T052 |
| FR-004-31 | T005, T046, T054 |
| FR-004-32 | T002, T003, T059 |
| SC-001 | T023 |
| SC-002 | T024 |
| SC-003 | T031 |
| SC-004, 005 | T053 |
| SC-006 | T050 |
| SC-007 | T042, T045 |
| SC-008 | T037, T054 |
| SC-009 | T016, T030 |

## Notes

- [P] = archivos distintos y sin dependencias pendientes.
- La etiqueta [Story] vincula cada tarea con su historia.
- Verificar que los tests fallan antes de implementar; si un test pasa sin código nuevo, hacer una prueba de mutación (acuerdo del handoff §7).
- Parar en cada checkpoint para validar la historia.
- Evitar: tareas vagas, conflictos en el mismo archivo y dependencias entre historias que rompan su independencia.
