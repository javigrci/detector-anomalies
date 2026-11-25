"""Dataset de vectores, huella determinista y separación temporal (research R2, R3).

El dataset son los vectores del incremento 3 ordenados por ``(timestamp, source, event_id)`` con la
identidad de su esquema. La separación es en tres bloques contiguos y los eventos con el mismo
``timestamp`` nunca se reparten entre dos conjuntos.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine

from security_anomaly.features import FEATURE_SCHEMA, features_for_range
from security_anomaly.ml.errors import MlError
from security_anomaly.schemas.features import FeatureVector
from security_anomaly.schemas.ml import MlPolicy


@dataclass(frozen=True)
class TrainingDataset:
    """Vectores ordenados y la versión y huella del esquema con el que se calcularon."""

    vectors: tuple[FeatureVector, ...]
    schema_version: int
    schema_fingerprint: str


@dataclass(frozen=True)
class Partition:
    """Entrenamiento (el más antiguo), calibración y prueba (el más reciente): bloques contiguos."""

    train: tuple[FeatureVector, ...]
    calibration: tuple[FeatureVector, ...]
    test: tuple[FeatureVector, ...]
    schema_version: int
    schema_fingerprint: str


def _order_key(vector: FeatureVector) -> tuple[datetime, str, str]:
    return (vector.timestamp, vector.source, vector.event_id)


def make_dataset(vectors: Iterable[FeatureVector]) -> TrainingDataset:
    """Ordena los vectores y comprueba que todos tienen el esquema de características esperado."""
    ordered = sorted(vectors, key=_order_key)
    for vector in ordered:
        if vector.schema_version != FEATURE_SCHEMA.version or tuple(vector.features) != (
            FEATURE_SCHEMA.names
        ):
            raise MlError("invalid_schema")
    return TrainingDataset(tuple(ordered), FEATURE_SCHEMA.version, FEATURE_SCHEMA.fingerprint)


def build_dataset(
    engine: Engine, start: datetime, end: datetime, *, history_start: datetime
) -> TrainingDataset:
    """Dataset de los vectores de los eventos guardados en ``[start, end)``."""
    return make_dataset(features_for_range(engine, start, end, history_start=history_start))


def _encode(value: object) -> str:
    return value.hex() if isinstance(value, float) else str(value)


def dataset_fingerprint(dataset: TrainingDataset) -> str:
    """SHA-256 del esquema y, en orden, de la identidad y los valores de cada vector."""
    digest = hashlib.sha256()
    digest.update(f"{dataset.schema_version}\x1f{dataset.schema_fingerprint}\x1d".encode())
    for vector in dataset.vectors:
        fields = [
            vector.source,
            vector.event_id,
            vector.timestamp.isoformat(),
            str(vector.schema_version),
            *(_encode(vector.features[name]) for name in FEATURE_SCHEMA.names),
        ]
        digest.update("\x1f".join(fields).encode())
        digest.update(b"\x1e")
    return digest.hexdigest()


def _advance_past_ties(vectors: tuple[FeatureVector, ...], index: int) -> int:
    """Mueve una frontera al siguiente instante distinto para no partir un ``timestamp``."""
    while 0 < index < len(vectors) and vectors[index].timestamp == vectors[index - 1].timestamp:
        index += 1
    return index


def split_temporal(dataset: TrainingDataset, policy: MlPolicy) -> Partition:
    """Tres bloques contiguos: entrenamiento, calibración y prueba (research R3)."""
    vectors = dataset.vectors
    n = len(vectors)
    first = _advance_past_ties(vectors, int(policy.train_fraction * n))
    second = _advance_past_ties(vectors, first + int(policy.calibration_fraction * n))
    train, calibration, test = vectors[:first], vectors[first:second], vectors[second:]
    if min(len(train), len(calibration), len(test)) < policy.min_events_per_set:
        raise MlError("insufficient_data")
    return Partition(train, calibration, test, dataset.schema_version, dataset.schema_fingerprint)
