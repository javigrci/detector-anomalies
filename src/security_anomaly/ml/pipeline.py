"""Transformaciones, Isolation Forest y calibración: el pipeline de entrenamiento y puntuación.

Entrenamiento e inferencia pasan por el mismo código (Principio III). Cada pieza se ajusta solo
con su propio conjunto: transformaciones y bosque con entrenamiento, calibración con calibración.
"""

from dataclasses import dataclass

import numpy as np
import scipy
import sklearn
from numpy.typing import NDArray
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

from security_anomaly.features import FEATURE_SCHEMA
from security_anomaly.ml.dataset import Partition
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.scoring import make_score, raw_scores
from security_anomaly.schemas.features import FeatureVector
from security_anomaly.schemas.ml import MlPolicy, Score

SEED = 42
_NUMERIC = [i for i, d in enumerate(FEATURE_SCHEMA.definitions) if d.kind != "category"]
_CATEGORICAL = [i for i, d in enumerate(FEATURE_SCHEMA.definitions) if d.kind == "category"]


@dataclass
class TrainedModel:
    """Transformaciones ajustadas, bosque y calibración, con el esquema y las versiones usadas."""

    transformer: ColumnTransformer
    forest: IsolationForest
    calibration: NDArray[np.float64]
    schema_version: int
    schema_fingerprint: str
    policy: MlPolicy
    library_versions: dict[str, str]


def library_versions() -> dict[str, str]:
    """Versiones de las librerías cuyo comportamiento afecta al modelo serializado."""
    return {
        "scikit-learn": sklearn.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }


def feature_matrix(
    vectors: "list[FeatureVector] | tuple[FeatureVector, ...]",
) -> NDArray[np.object_]:
    """Matriz de objetos con una columna por característica del esquema, en su orden."""
    matrix = np.empty((len(vectors), len(FEATURE_SCHEMA.names)), dtype=object)
    for row, vector in enumerate(vectors):
        for column, name in enumerate(FEATURE_SCHEMA.names):
            matrix[row, column] = vector.features[name]
    return matrix


def _to_float(values: NDArray[np.object_]) -> NDArray[np.float64]:
    return np.asarray(values, dtype=np.float64)


def _build_transformer() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("numeric", FunctionTransformer(_to_float, validate=False), _NUMERIC),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float64),
                _CATEGORICAL,
            ),
        ],
        sparse_threshold=0.0,
    )


def train_model(partition: Partition, policy: MlPolicy) -> TrainedModel:
    """Ajusta transformaciones y bosque con entrenamiento y la calibración con calibración."""
    if isinstance(policy.max_samples, int) and policy.max_samples > len(partition.train):
        raise MlError("invalid_parameters")
    transformer = _build_transformer()
    train_matrix = transformer.fit_transform(feature_matrix(partition.train))
    forest = IsolationForest(
        n_estimators=policy.n_estimators,
        max_samples=policy.max_samples,
        random_state=SEED,
        n_jobs=1,
    ).fit(train_matrix)
    calibration_matrix = transformer.transform(feature_matrix(partition.calibration))
    calibration = np.sort(raw_scores(forest, calibration_matrix))
    return TrainedModel(
        transformer=transformer,
        forest=forest,
        calibration=calibration,
        schema_version=partition.schema_version,
        schema_fingerprint=partition.schema_fingerprint,
        policy=policy,
        library_versions=library_versions(),
    )


def score_vectors(
    model: TrainedModel, vectors: "list[FeatureVector] | tuple[FeatureVector, ...]"
) -> list[Score]:
    """Puntúa vectores con el modelo; rechaza los que no tienen el esquema del modelo."""
    if (
        model.schema_version != FEATURE_SCHEMA.version
        or model.schema_fingerprint != FEATURE_SCHEMA.fingerprint
    ):
        raise MlError("incompatible_features")
    for vector in vectors:
        if vector.schema_version != model.schema_version or tuple(vector.features) != (
            FEATURE_SCHEMA.names
        ):
            raise MlError("incompatible_features")
    if not vectors:
        return []
    matrix = model.transformer.transform(feature_matrix(vectors))
    raw = raw_scores(model.forest, matrix)
    return [make_score(float(value), model.calibration, model.policy) for value in raw]


def score_vector(model: TrainedModel, vector: FeatureVector) -> Score:
    """Puntúa un vector con el modelo."""
    return score_vectors(model, [vector])[0]
