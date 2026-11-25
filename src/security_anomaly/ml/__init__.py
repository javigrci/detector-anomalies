"""Entrenamiento, calibración, evaluación y versionado del modelo (incremento 4).

API pública: ver ``specs/004-model-training/contracts/ml-api.md``. La puntuación de anomalía es un
percentil frente a la calibración; no es una probabilidad de ataque.
"""

from security_anomaly.ml.config import MlSettings, load_ml_settings
from security_anomaly.ml.dataset import (
    Partition,
    TrainingDataset,
    build_dataset,
    dataset_fingerprint,
    make_dataset,
    split_temporal,
)
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.evaluation import evaluate
from security_anomaly.ml.pipeline import TrainedModel, score_vector, score_vectors, train_model
from security_anomaly.ml.registry import (
    activate_version,
    get_active_version,
    get_training_run,
    list_training_runs,
    list_versions,
    load_active_model,
    load_model,
)
from security_anomaly.ml.service import TrainingResult, run_training
from security_anomaly.schemas.ml import (
    EvaluationReport,
    MlPolicy,
    ModelVersion,
    Score,
    TrainingRun,
)

__all__ = [
    "EvaluationReport",
    "MlError",
    "MlPolicy",
    "MlSettings",
    "ModelVersion",
    "Partition",
    "Score",
    "TrainedModel",
    "TrainingDataset",
    "TrainingResult",
    "TrainingRun",
    "activate_version",
    "build_dataset",
    "dataset_fingerprint",
    "evaluate",
    "get_active_version",
    "get_training_run",
    "list_training_runs",
    "list_versions",
    "load_active_model",
    "load_ml_settings",
    "load_model",
    "make_dataset",
    "run_training",
    "score_vector",
    "score_vectors",
    "split_temporal",
    "train_model",
]
