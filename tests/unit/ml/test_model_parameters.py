"""FR-004-08, 13: el bosque, sus parámetros y la calibración."""

import numpy as np
import pytest

from security_anomaly.ml.dataset import Partition, make_dataset, split_temporal
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.pipeline import feature_matrix, train_model
from security_anomaly.ml.scoring import raw_scores
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import synthetic_vectors


def _partition(policy: MlPolicy | None = None) -> Partition:
    return split_temporal(make_dataset(synthetic_vectors(4, 1500).vectors), policy or MlPolicy())


def test_the_forest_uses_seed_42_default_contamination_and_one_job() -> None:
    model = train_model(_partition(), MlPolicy())
    params = model.forest.get_params()
    assert params["random_state"] == 42
    assert params["contamination"] == "auto"  # nunca se fija
    assert params["n_jobs"] == 1


def test_the_hyperparameters_reach_the_forest() -> None:
    policy = MlPolicy(n_estimators=25, max_samples=64)
    model = train_model(_partition(policy), policy)
    assert len(model.forest.estimators_) == 25
    assert model.forest.max_samples == 64


def test_a_sample_size_larger_than_the_training_set_is_rejected_before_training() -> None:
    policy = MlPolicy(max_samples=10_000_000)
    with pytest.raises(MlError) as caught:
        train_model(_partition(), policy)
    assert caught.value.code == "invalid_parameters"


def test_the_calibration_is_the_sorted_raw_scores_of_the_calibration_set_only() -> None:
    partition = _partition()
    model = train_model(partition, MlPolicy())
    expected = np.sort(
        raw_scores(model.forest, model.transformer.transform(feature_matrix(partition.calibration)))
    )
    assert np.array_equal(model.calibration, expected)
    assert len(model.calibration) == len(partition.calibration)
    assert np.all(np.diff(model.calibration) >= 0)


def test_the_model_records_its_schema_policy_and_library_versions() -> None:
    model = train_model(_partition(), MlPolicy())
    assert model.schema_version == 1 and len(model.schema_fingerprint) == 64
    assert model.policy == MlPolicy()
    assert set(model.library_versions) == {"scikit-learn", "numpy", "scipy"}
