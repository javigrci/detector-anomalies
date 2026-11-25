"""FR-004-17, 20: evaluación sin etiquetas (distribución, estabilidad, alertas, contexto)."""

import numpy as np

from security_anomaly.ml.dataset import Partition, make_dataset, split_temporal
from security_anomaly.ml.evaluation import evaluate
from security_anomaly.ml.pipeline import TrainedModel, score_vectors, train_model
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import synthetic_vectors


def _setup() -> tuple[TrainedModel, Partition]:
    data = synthetic_vectors(7, 3000)
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    return train_model(partition, MlPolicy()), partition


def test_the_distribution_of_scores() -> None:
    model, partition = _setup()
    report = evaluate(model, partition)
    scores = np.array([s.anomaly_score for s in score_vectors(model, partition.test)])
    assert report.n_test == len(partition.test)
    assert report.score_mean == float(scores.mean())
    keys = ["p0", "p50", "p90", "p95", "p99", "p100"]
    assert list(report.score_quantiles) == keys
    values = [report.score_quantiles[k] for k in keys]
    assert values == sorted(values) and values[0] >= 0.0 and values[-1] <= 1.0
    assert report.score_quantiles["p0"] == float(scores.min())
    assert report.score_quantiles["p100"] == float(scores.max())


def test_the_alert_rate_uses_the_operational_threshold() -> None:
    model, partition = _setup()
    report = evaluate(model, partition)
    flags = [s.is_anomaly for s in score_vectors(model, partition.test)]
    assert report.alert_rate == sum(flags) / len(flags)


def test_temporal_stability_is_four_consecutive_segments() -> None:
    model, partition = _setup()
    report = evaluate(model, partition)
    scores = score_vectors(model, partition.test)
    segments = report.temporal_stability
    assert [s.index for s in segments] == [0, 1, 2, 3]
    assert sum(s.n for s in segments) == len(scores)
    start = 0
    for segment in segments:
        chunk = scores[start : start + segment.n]
        start += segment.n
        assert segment.mean_score == float(np.mean([s.anomaly_score for s in chunk]))
        assert segment.alert_rate == sum(s.is_anomaly for s in chunk) / segment.n
    rates = [s.alert_rate for s in segments]
    assert report.max_alert_rate_gap == max(rates) - min(rates)


def test_incomplete_contexts_are_counted_per_set() -> None:
    model, partition = _setup()
    report = evaluate(model, partition)
    for name, vectors in (
        ("train", partition.train),
        ("calibration", partition.calibration),
        ("test", partition.test),
    ):
        assert report.incomplete_context[name] == sum(not v.context_complete for v in vectors)


def test_without_labels_there_are_no_classification_metrics() -> None:
    model, partition = _setup()
    report = evaluate(model, partition)
    assert report.labelled is False and report.classification is None
    text = report.model_dump_json().lower()
    for word in ("precision", "recall", "f1", "pr_auc"):
        assert f'"{word}"' not in text
