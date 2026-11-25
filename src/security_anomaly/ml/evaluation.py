"""Evaluación del modelo con y sin etiquetas, con sus limitaciones (research R7; SPEC §5.4).

Se mide sobre el conjunto de prueba. Las etiquetas son externas y opcionales y nunca influyen en el
ajuste ni en la calibración. El informe no promete ninguna precisión mínima.
"""

from collections.abc import Mapping, Sequence

import numpy as np
from sklearn.metrics import average_precision_score

from security_anomaly.ml.dataset import Partition
from security_anomaly.ml.pipeline import TrainedModel, score_vectors
from security_anomaly.schemas.features import FeatureVector
from security_anomaly.schemas.ml import (
    ClassificationMetrics,
    EvaluationReport,
    Score,
    StabilitySegment,
)

QUANTILES = {"p0": 0.0, "p50": 0.5, "p90": 0.9, "p95": 0.95, "p99": 0.99, "p100": 1.0}
SEGMENTS = 4
NORMAL_LABEL = "normal"

LIMITATIONS: tuple[str, ...] = (
    "Los datos de prueba son sintéticos: validan el software, "
    "no demuestran capacidad real de detección.",
    "Los umbrales de severidad y el umbral operativo son provisionales "
    "y deben validarse con datos reales.",
    "La puntuación de anomalía es un percentil frente a la calibración, "
    "no una probabilidad de ataque.",
    "No se promete ninguna precisión mínima: sin un dataset etiquetado "
    "y una evaluación válida no hay garantía.",
)


def classification_metrics(
    y_true: Sequence[int], flagged: Sequence[bool], scores: Sequence[float]
) -> ClassificationMetrics:
    """Precision, recall, F1, PR-AUC y matriz de confusión; «no calculables» si falta una clase."""
    truth = np.asarray(y_true, dtype=int)
    flags = np.asarray(flagged, dtype=bool)
    tp = int(np.sum(flags & (truth == 1)))
    fp = int(np.sum(flags & (truth == 0)))
    fn = int(np.sum(~flags & (truth == 1)))
    tn = int(np.sum(~flags & (truth == 0)))
    confusion = {"tp": tp, "fp": fp, "tn": tn, "fn": fn}
    positives, negatives = tp + fn, tn + fp
    reason = None
    if positives + negatives == 0:
        reason = "sin eventos etiquetados en el conjunto de prueba"
    elif positives == 0:
        reason = "sin positivos en el conjunto de prueba"
    elif negatives == 0:
        reason = "sin negativos en el conjunto de prueba"
    if reason is not None:
        return ClassificationMetrics(
            calculable=False,
            precision=None,
            recall=None,
            f1=None,
            pr_auc=None,
            confusion=confusion,
            reason=reason,
        )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positives
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ClassificationMetrics(
        calculable=True,
        precision=precision,
        recall=recall,
        f1=f1,
        pr_auc=float(average_precision_score(truth, np.asarray(scores, dtype=float))),
        confusion=confusion,
        reason=None,
    )


def _incomplete(vectors: Sequence[FeatureVector]) -> int:
    return sum(not v.context_complete for v in vectors)


def _segments(scores: Sequence[Score]) -> tuple[StabilitySegment, ...]:
    count = min(SEGMENTS, len(scores))
    segments = []
    for index, chunk in enumerate(np.array_split(np.arange(len(scores)), count)):
        group = [scores[int(i)] for i in chunk]
        segments.append(
            StabilitySegment(
                index=index,
                n=len(group),
                mean_score=float(np.mean([s.anomaly_score for s in group])),
                alert_rate=sum(s.is_anomaly for s in group) / len(group),
            )
        )
    return tuple(segments)


def evaluate(
    model: TrainedModel, partition: Partition, *, labels: Mapping[str, str] | None = None
) -> EvaluationReport:
    """Informe sobre el conjunto de prueba; con ``labels`` añade las métricas de clasificación.

    Una etiqueta de un evento que no está en la prueba se ignora, y un evento de la prueba sin
    etiqueta no entra en las métricas de clasificación.
    """
    test = partition.test
    scores = score_vectors(model, test)
    anomaly = np.array([s.anomaly_score for s in scores], dtype=float)
    segments = _segments(scores)
    rates = [s.alert_rate for s in segments]
    classification = None
    if labels is not None:
        rows = [(v, s) for v, s in zip(test, scores, strict=True) if v.event_id in labels]
        classification = classification_metrics(
            [0 if labels[v.event_id] == NORMAL_LABEL else 1 for v, _ in rows],
            [s.is_anomaly for _, s in rows],
            [s.anomaly_score for _, s in rows],
        )
    return EvaluationReport(
        n_test=len(test),
        score_mean=float(anomaly.mean()),
        score_quantiles={k: float(np.quantile(anomaly, q)) for k, q in QUANTILES.items()},
        alert_rate=sum(s.is_anomaly for s in scores) / len(scores),
        temporal_stability=segments,
        max_alert_rate_gap=max(rates) - min(rates),
        incomplete_context={
            "train": _incomplete(partition.train),
            "calibration": _incomplete(partition.calibration),
            "test": _incomplete(test),
        },
        labelled=labels is not None,
        classification=classification,
        limitations=LIMITATIONS,
    )
