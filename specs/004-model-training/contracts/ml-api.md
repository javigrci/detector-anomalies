# Contrato: API pública del entrenamiento

La consumen la CLI de operación y el incremento 5 (inferencia). Todo se importa de `security_anomaly.ml`.

## Funciones

```python
build_dataset(engine: Engine, start: datetime, end: datetime, *, history_start: datetime) -> TrainingDataset
```
Lee los vectores de `[start, end)` con `features_for_range` (rol `anomaly_app`), comprueba que todos tienen el
esquema esperado y los devuelve ordenados. `MlError("invalid_schema")` si no.

```python
dataset_fingerprint(dataset: TrainingDataset) -> str
split_temporal(dataset: TrainingDataset, policy: MlPolicy) -> Partition
```
Huella SHA-256 determinista; separación en tres bloques contiguos (los empatados de instante quedan juntos).
`MlError("insufficient_data")` si algún conjunto queda por debajo del mínimo.

```python
train_model(partition: Partition, policy: MlPolicy) -> TrainedModel
```
Ajusta transformaciones y bosque **solo** con entrenamiento y la calibración solo con calibración.

```python
score_vectors(model: TrainedModel, vectors: Sequence[FeatureVector]) -> list[Score]
score_vector(model: TrainedModel, vector: FeatureVector) -> Score
```
`raw_score = -score_samples`, `anomaly_score` percentil en [0, 1], `severity` y `is_anomaly`.
`MlError("incompatible_features")` si el vector no tiene el esquema (versión y huella) del modelo.

```python
evaluate(model: TrainedModel, partition: Partition, *, labels: Mapping[str, str] | None = None) -> EvaluationReport
```
Informe sobre el conjunto de prueba; con `labels` añade precision, recall, F1, PR-AUC y matriz de confusión.

```python
run_training(engine: Engine, settings: MlSettings, start: datetime, end: datetime, *, history_start: datetime,
             policy: MlPolicy | None = None, labels: Mapping[str, str] | None = None) -> TrainingResult
```
Orquesta: marca como fallidos los entrenamientos caducados, registra el entrenamiento (`running`; concurrencia 1),
construye el dataset, separa, entrena, evalúa, guarda el artefacto y registra la versión. **No la activa.** Un
fallo deja el registro en `failed`, sin versión ni archivo huérfano.

```python
activate_version(engine: Engine, settings: MlSettings, version: str, *, approved: bool) -> ModelVersion
get_active_version(engine: Engine) -> ModelVersion | None
get_training_run(engine: Engine, run_id: UUID) -> TrainingRun
list_versions(engine: Engine) -> list[ModelVersion]
load_model(engine: Engine, settings: MlSettings, version: str) -> TrainedModel
load_active_model(engine: Engine, settings: MlSettings) -> TrainedModel
```
`activate_version` sin `approved=True` → `MlError("approval_required")` sin tocar la base de datos. Activar deja
una sola versión activa y verifica la integridad del artefacto antes. `load_model` solo abre
`MODEL_DIR/<artifact_file registrado>`, tras comprobar ruta, huella y versiones de librerías.

## Garantías

- **Reproducibilidad:** mismos datos, parámetros y entorno bloqueado → puntuaciones idénticas.
- **Sin fuga:** transformaciones, modelo y calibración dependen solo de su conjunto.
- **Mismo pipeline:** el modelo cargado puntúa igual que el recién entrenado.
- **Carga segura:** nada se deserializa fuera de `MODEL_DIR` ni sin verificar la huella.
- **Humano al mando:** ningún entrenamiento activa su resultado; no hay reentrenamiento automático.
- **Privacidad:** artefactos, registros, informes, errores y logs sin identificadores ni valores de datos.
- **Honestidad:** `anomaly_score` es un percentil; nunca una probabilidad.

## Excepciones

| Excepción | Cuándo | Atributos |
|---|---|---|
| `MlError` | entrada o estado inválido (ver códigos en `data-model.md`) | `code` fijo, mensaje fijo |
| `FeatureError` | `history_start` inválido o eventos anteriores a él | heredado del incremento 3 |
| `StorageError` | falla la base de datos | heredado del incremento 2 |
| `ConfigError` | configuración inválida | heredado |

## Correspondencia con SPEC (para el incremento 5)

- `POST /api/v1/models/train` → `run_training` en un proceso aparte; `GET …/train/{run_id}` → `get_training_run`.
- `POST /api/v1/models/{version}/activate` → `activate_version(approved=True)` con rol `admin`.
- `GET /api/v1/models/active` → `get_active_version`; puntuar → `load_active_model` + `score_vector`.
- `503` sin modelo activo → `MlError("no_active_model")`.
