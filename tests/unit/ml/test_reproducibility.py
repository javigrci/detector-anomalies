"""SC-001, FR-004-09: el mismo dataset y los mismos parámetros dan el mismo modelo."""

import subprocess
import sys
from pathlib import Path

import numpy as np

from security_anomaly.ml.dataset import Partition, dataset_fingerprint, make_dataset, split_temporal
from security_anomaly.ml.pipeline import TrainedModel, feature_matrix, train_model
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import model_digest, synthetic_vectors

ROOT = Path(__file__).resolve().parents[3]

_SCRIPT = """
import hashlib, sys
sys.path.insert(0, ".")
from security_anomaly.ml.dataset import dataset_fingerprint, make_dataset, split_temporal
from security_anomaly.ml.dataset import Partition
from security_anomaly.ml.pipeline import TrainedModel, feature_matrix, train_model
from security_anomaly.ml.scoring import raw_scores
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import model_digest, synthetic_vectors
data = synthetic_vectors(5, 1200)
dataset = make_dataset(data.vectors)
part = split_temporal(dataset, MlPolicy())
model = train_model(part, MlPolicy())
raw = raw_scores(model.forest, model.transformer.transform(feature_matrix(part.test)))
print(dataset_fingerprint(dataset), model_digest(model), hashlib.sha256(raw.tobytes()).hexdigest())
"""


def _train(seed: int) -> tuple[TrainedModel, Partition]:
    data = synthetic_vectors(seed, 1200)
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    return train_model(partition, MlPolicy()), partition


def test_two_trainings_give_identical_scores_and_summary() -> None:
    (a, part_a), (b, _) = _train(5), _train(5)
    x = feature_matrix(part_a.test)
    from security_anomaly.ml.scoring import raw_scores

    raw_a = raw_scores(a.forest, a.transformer.transform(x))
    raw_b = raw_scores(b.forest, b.transformer.transform(x))
    assert np.array_equal(raw_a, raw_b)
    assert model_digest(a) == model_digest(b)
    assert np.array_equal(a.calibration, b.calibration)


def test_a_different_dataset_gives_a_different_model() -> None:
    (a, _), (b, _) = _train(5), _train(6)
    assert model_digest(a) != model_digest(b)


def test_the_result_does_not_depend_on_the_hash_seed_or_the_process() -> None:
    outputs = set()
    for seed in ("0", "1", "4242", "random"):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _SCRIPT],
            cwd=ROOT,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout.strip())
    assert len(outputs) == 1
    fingerprint = next(iter(outputs)).split()[0]
    data = synthetic_vectors(5, 1200)
    assert fingerprint == dataset_fingerprint(make_dataset(data.vectors))
