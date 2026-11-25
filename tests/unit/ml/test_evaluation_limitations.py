"""FR-004-19: el informe documenta las limitaciones y no promete una precisión mínima."""

import re

from security_anomaly.ml.dataset import make_dataset, split_temporal
from security_anomaly.ml.evaluation import LIMITATIONS, evaluate
from security_anomaly.ml.pipeline import train_model
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import synthetic_vectors


def test_the_report_carries_the_fixed_limitations() -> None:
    data = synthetic_vectors(8, 3000)
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    report = evaluate(train_model(partition, MlPolicy()), partition, labels=data.labels)
    assert report.limitations == LIMITATIONS
    text = " ".join(report.limitations).lower()
    assert "sintétic" in text
    assert "provisional" in text
    assert "no demuestran" in text or "no demuestra" in text


def test_no_minimum_precision_is_promised() -> None:
    text = " ".join(LIMITATIONS)
    assert "no se promete" in text.lower()
    assert not re.search(r"\d\s*%", text)
    assert not re.search(r"precisi[oó]n\s+(m[ií]nima\s+)?(de|superior|mayor)", text.lower())


def test_the_serialized_report_has_no_event_values() -> None:
    data = synthetic_vectors(8, 3000)
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    report = evaluate(train_model(partition, MlPolicy()), partition, labels=data.labels)
    text = report.model_dump_json()
    for vector in partition.test[:30]:
        assert vector.event_id not in text
