"""FR-004-14, 15: severidad por umbrales configurables y bandera de anomalía."""

import pytest

from security_anomaly.ml.errors import MlError
from security_anomaly.ml.scoring import is_anomaly_of, severity_of


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, "low"),
        (0.79, "low"),
        (0.80, "medium"),
        (0.94, "medium"),
        (0.95, "high"),
        (1.0, "high"),
    ],
)
def test_default_thresholds(score: float, expected: str) -> None:
    assert severity_of(score, medium=0.80, high=0.95) == expected


def test_custom_thresholds_are_applied() -> None:
    assert severity_of(0.55, medium=0.5, high=0.6) == "medium"
    assert severity_of(0.6, medium=0.5, high=0.6) == "high"
    assert severity_of(0.49, medium=0.5, high=0.6) == "low"


def test_equal_thresholds_make_medium_unreachable_below_high() -> None:
    assert severity_of(0.89, medium=0.9, high=0.9) == "low"
    assert severity_of(0.9, medium=0.9, high=0.9) == "high"


@pytest.mark.parametrize(
    ("medium", "high"), [(0.9, 0.8), (0.0, 0.5), (-0.1, 0.5), (0.5, 1.1), (1.2, 1.5)]
)
def test_incoherent_thresholds_are_rejected_without_values(medium: float, high: float) -> None:
    with pytest.raises(MlError) as caught:
        severity_of(0.5, medium=medium, high=high)
    assert caught.value.code == "invalid_parameters"
    assert str(medium) not in str(caught.value) or medium == 0.0


@pytest.mark.parametrize(
    ("score", "expected"), [(0.79, False), (0.80, True), (0.99, True), (1.0, True)]
)
def test_is_anomaly_from_the_operational_threshold(score: float, expected: bool) -> None:
    assert is_anomaly_of(score, 0.80) is expected


def test_a_custom_operational_threshold_and_validation() -> None:
    assert is_anomaly_of(0.5, 0.5) is True
    assert is_anomaly_of(0.49, 0.5) is False
    for bad in (-0.1, 1.1):
        with pytest.raises(MlError) as caught:
            is_anomaly_of(0.5, bad)
        assert caught.value.code == "invalid_parameters"
