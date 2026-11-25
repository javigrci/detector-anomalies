"""FR-004-01: `build_dataset` lee los vectores de eventos guardados con el incremento 2."""

from datetime import timedelta

import pytest
from sqlalchemy import Engine

from security_anomaly.features import compute_features
from security_anomaly.ml.dataset import build_dataset
from security_anomaly.storage import save_events
from tests.ml_factory import synthetic_vectors

pytestmark = pytest.mark.integration


def test_the_dataset_equals_the_in_memory_vectors_of_the_range(app_engine: Engine) -> None:
    data = synthetic_vectors(2, 800)
    save_events(app_engine, data.events)
    first = min(e.timestamp for e in data.events)
    last = max(e.timestamp for e in data.events)
    history_start = first - timedelta(hours=1)
    dataset = build_dataset(
        app_engine, first, last + timedelta(seconds=1), history_start=history_start
    )
    expected = list(compute_features(data.events, history_start=history_start))
    assert list(dataset.vectors) == expected
    assert dataset.schema_version == 1


def test_an_empty_range_gives_an_empty_dataset(app_engine: Engine) -> None:
    data = synthetic_vectors(2, 300)
    start = min(e.timestamp for e in data.events)
    dataset = build_dataset(
        app_engine, start, start + timedelta(seconds=5), history_start=start - timedelta(hours=1)
    )
    assert dataset.vectors == ()
