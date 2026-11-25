"""SC-003: las ráfagas de fallos inyectadas puntúan más alto que el tráfico normal."""

import numpy as np
import pytest

from security_anomaly.ml.dataset import make_dataset, split_temporal
from security_anomaly.ml.pipeline import score_vectors, train_model
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import synthetic_vectors


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_burst_events_score_higher_than_normal_traffic(seed: int) -> None:
    data = synthetic_vectors(seed, 6000, burst_count=20, burst_size=30)
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    model = train_model(partition, MlPolicy())
    scores = score_vectors(model, partition.test)
    burst = [
        s
        for v, s in zip(partition.test, scores, strict=True)
        if data.labels[v.event_id] == "failure_burst"
    ]
    normal = [
        s
        for v, s in zip(partition.test, scores, strict=True)
        if data.labels[v.event_id] == "normal"
    ]
    assert len(burst) >= 20 and len(normal) >= 200
    assert np.mean([s.anomaly_score for s in burst]) > np.mean([s.anomaly_score for s in normal])
    share = sum(s.is_anomaly for s in burst) / len(burst)
    assert share > 0.5
