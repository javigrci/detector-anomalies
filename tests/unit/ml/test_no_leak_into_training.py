"""SC-002, FR-004-10, 13 (puerta de aceptación): calibración y prueba no llegan al ajuste."""

from dataclasses import replace

import pytest

from security_anomaly.ml.dataset import Partition, make_dataset, split_temporal
from security_anomaly.ml.pipeline import train_model
from security_anomaly.schemas.features import FeatureVector
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import (
    calibration_digest,
    forest_digest,
    synthetic_vectors,
    transformer_digest,
    tweak,
)

SEEDS = range(1, 8)


def _mutate(vectors: tuple[FeatureVector, ...]) -> dict[str, tuple[FeatureVector, ...]]:
    changed = tuple(
        tweak(v, ip_event_count=int(v.features["ip_event_count"]) + 7, source="mutated-source")
        for v in vectors
    )
    extra = tuple(
        v.model_copy(update={"event_id": f"extra-{i}"}) for i, v in enumerate(vectors[:25])
    )
    return {
        "changed": changed,
        "removed": vectors[::2],
        "added": (*vectors, *extra),
    }


def _partition(seed: int) -> Partition:
    return split_temporal(make_dataset(synthetic_vectors(seed, 1500).vectors), MlPolicy())


@pytest.mark.parametrize("seed", SEEDS)
def test_changing_calibration_or_test_never_changes_the_fit(seed: int) -> None:
    part = _partition(seed)
    base = train_model(part, MlPolicy())
    for name, mutated in _mutate(part.test).items():
        other = train_model(replace(part, test=mutated), MlPolicy())
        assert transformer_digest(other) == transformer_digest(base), name
        assert forest_digest(other) == forest_digest(base), name
        assert calibration_digest(other) == calibration_digest(base), name  # la prueba no calibra
    for name, mutated in _mutate(part.calibration).items():
        other = train_model(replace(part, calibration=mutated), MlPolicy())
        assert transformer_digest(other) == transformer_digest(base), name
        assert forest_digest(other) == forest_digest(base), name


@pytest.mark.parametrize("seed", SEEDS)
def test_changing_the_calibration_set_only_changes_the_calibration(seed: int) -> None:
    part = _partition(seed)
    base = train_model(part, MlPolicy())
    other = train_model(replace(part, calibration=_mutate(part.calibration)["changed"]), MlPolicy())
    assert calibration_digest(other) != calibration_digest(base)


@pytest.mark.parametrize("seed", SEEDS)
def test_changing_the_training_set_does_change_the_fit(seed: int) -> None:
    part = _partition(seed)
    base = train_model(part, MlPolicy())
    other = train_model(replace(part, train=_mutate(part.train)["changed"]), MlPolicy())
    assert transformer_digest(other) != transformer_digest(base)  # aprende la categoría nueva
    assert forest_digest(other) != forest_digest(base)
