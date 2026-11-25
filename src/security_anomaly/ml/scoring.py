"""Puntuación bruta, percentil de calibración, severidad y bandera (SPEC §5.3; research R6).

``raw_score = -score_samples(X)``: mayor valor implica mayor anomalía. ``anomaly_score`` es el
percentil de la puntuación bruta frente a la distribución de calibración, en [0, 1]; no es una
probabilidad de ataque y nunca debe presentarse como tal.
"""

from typing import Any

import numpy as np
from numpy.typing import NDArray

from security_anomaly.ml.errors import MlError
from security_anomaly.schemas.ml import MlPolicy, Score, Severity

Floats = NDArray[np.float64]


def raw_scores(forest: Any, matrix: Any) -> Floats:
    """Puntuación bruta: ``-score_samples`` (mayor valor, más anómalo)."""
    return np.asarray(-forest.score_samples(matrix), dtype=np.float64)


def percentile(calibration: Floats, raw: Any) -> Any:
    """Fracción de puntuaciones de calibración menores o iguales a ``raw``, en [0, 1].

    ``calibration`` debe estar ordenada de menor a mayor. Es 1 si ``raw`` supera a todas y 0 si es
    menor que todas; es monótona en ``raw``.
    """
    if len(calibration) == 0:
        raise MlError("invalid_parameters")
    return np.searchsorted(calibration, raw, side="right") / len(calibration)


def check_thresholds(medium: float, high: float, operational: float | None = None) -> None:
    """Valida ``0 < medium <= high <= 1`` y, si se da, el umbral operativo en [0, 1]."""
    if not 0 < medium <= high <= 1:
        raise MlError("invalid_parameters")
    if operational is not None and not 0 <= operational <= 1:
        raise MlError("invalid_parameters")


def severity_of(anomaly_score: float, *, medium: float, high: float) -> Severity:
    """``low`` por debajo de ``medium``, ``medium`` desde él y ``high`` desde ``high``."""
    check_thresholds(medium, high)
    if anomaly_score >= high:
        return "high"
    if anomaly_score >= medium:
        return "medium"
    return "low"


def is_anomaly_of(anomaly_score: float, threshold: float) -> bool:
    """Verdadero si la puntuación de anomalía alcanza el umbral operativo."""
    check_thresholds(0.5, 0.5, threshold)
    return anomaly_score >= threshold


def make_score(raw: float, calibration: Floats, policy: MlPolicy) -> Score:
    """Puntuación completa de un evento a partir de su puntuación bruta."""
    anomaly = float(percentile(calibration, raw))
    return Score(
        raw_score=float(raw),
        anomaly_score=anomaly,
        severity=severity_of(anomaly, medium=policy.severity_medium, high=policy.severity_high),
        is_anomaly=is_anomaly_of(anomaly, policy.anomaly_threshold),
    )
