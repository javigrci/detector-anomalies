"""FR-004-17, 18: evaluación con etiquetas externas solo sobre el conjunto de prueba."""

import numpy as np
from sklearn.metrics import average_precision_score

from security_anomaly.ml.dataset import Partition, make_dataset, split_temporal
from security_anomaly.ml.evaluation import classification_metrics, evaluate
from security_anomaly.ml.pipeline import TrainedModel, score_vectors, train_model
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import (
    calibration_digest,
    forest_digest,
    synthetic_vectors,
    transformer_digest,
)


def _setup() -> tuple[TrainedModel, Partition, dict[str, str]]:
    data = synthetic_vectors(7, 3000)
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    return train_model(partition, MlPolicy()), partition, dict(data.labels)


def test_a_small_case_calculated_by_hand() -> None:
    # reales [1, 1, 0, 0]; alertas [1, 0, 1, 0]; puntuaciones [0.9, 0.4, 0.6, 0.1]
    metrics = classification_metrics([1, 1, 0, 0], [True, False, True, False], [0.9, 0.4, 0.6, 0.1])
    assert metrics.calculable is True
    assert metrics.confusion == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert (metrics.precision, metrics.recall, metrics.f1) == (0.5, 0.5, 0.5)
    assert metrics.pr_auc == (1.0 + 2 / 3) / 2  # precisión en cada acierto: 1/1 y 2/3
    assert metrics.reason is None


def test_precision_is_zero_when_nothing_is_flagged() -> None:
    metrics = classification_metrics([1, 0, 0], [False, False, False], [0.3, 0.2, 0.1])
    assert (metrics.precision, metrics.recall, metrics.f1) == (0.0, 0.0, 0.0)


def test_without_one_class_the_metrics_are_not_calculable_and_never_divide_by_zero() -> None:
    no_pos = classification_metrics([0, 0, 0], [False, True, False], [0.1, 0.9, 0.2])
    assert no_pos.calculable is False and no_pos.reason is not None
    assert (no_pos.precision, no_pos.recall, no_pos.f1, no_pos.pr_auc) == (None, None, None, None)
    assert no_pos.confusion["fp"] == 1
    no_neg = classification_metrics([1, 1], [True, False], [0.9, 0.3])
    assert no_neg.calculable is False and no_neg.reason is not None
    empty = classification_metrics([], [], [])
    assert empty.calculable is False and empty.reason is not None


def test_the_labelled_report_matches_an_independent_computation() -> None:
    model, partition, labels = _setup()
    report = evaluate(model, partition, labels=labels)
    scores = score_vectors(model, partition.test)
    y_true = np.array([0 if labels[v.event_id] == "normal" else 1 for v in partition.test])
    flags = np.array([s.is_anomaly for s in scores])
    tp = int(np.sum(flags & (y_true == 1)))
    fp = int(np.sum(flags & (y_true == 0)))
    fn = int(np.sum(~flags & (y_true == 1)))
    assert report.labelled is True and report.classification is not None
    metrics = report.classification
    assert metrics.confusion == {"tp": tp, "fp": fp, "tn": len(y_true) - tp - fp - fn, "fn": fn}
    assert metrics.pr_auc == average_precision_score(y_true, [s.anomaly_score for s in scores])
    if tp + fp:
        assert metrics.precision == tp / (tp + fp)
    assert metrics.recall == tp / (tp + fn)


def test_only_the_test_set_labels_are_used_and_labels_of_other_events_are_ignored() -> None:
    model, partition, labels = _setup()
    train_ids = {v.event_id for v in partition.train}
    only_train = {k: v for k, v in labels.items() if k in train_ids}
    report = evaluate(model, partition, labels=only_train)
    assert report.classification is not None and report.classification.calculable is False
    extra = {**labels, "no-such-event": "failure_burst"}
    assert evaluate(model, partition, labels=extra) == evaluate(model, partition, labels=labels)


def test_labels_never_change_the_model_or_the_calibration() -> None:
    model, partition, labels = _setup()
    before = (transformer_digest(model), forest_digest(model), calibration_digest(model))
    scores_before = [s.anomaly_score for s in score_vectors(model, partition.test)]
    evaluate(model, partition, labels=labels)
    evaluate(model, partition)
    after = (transformer_digest(model), forest_digest(model), calibration_digest(model))
    assert before == after
    assert [s.anomaly_score for s in score_vectors(model, partition.test)] == scores_before


def test_the_distribution_part_is_identical_with_and_without_labels() -> None:
    model, partition, labels = _setup()
    a, b = evaluate(model, partition), evaluate(model, partition, labels=labels)
    assert a.model_copy(update={"labelled": True, "classification": b.classification}) == b
