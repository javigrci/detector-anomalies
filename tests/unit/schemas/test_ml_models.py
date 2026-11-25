"""FR-004-08, 14, 15: modelos del entrenamiento (política, puntuación, informe, registros)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from security_anomaly.schemas.ml import (
    ClassificationMetrics,
    EvaluationReport,
    MlPolicy,
    ModelVersion,
    Score,
    StabilitySegment,
    TrainingRun,
)


def test_policy_defaults() -> None:
    p = MlPolicy()
    assert (p.train_fraction, p.calibration_fraction, p.min_events_per_set) == (0.70, 0.15, 100)
    assert (p.n_estimators, p.max_samples) == (100, "auto")
    assert (p.severity_medium, p.severity_high, p.anomaly_threshold) == (0.80, 0.95, 0.80)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"train_fraction": 0},
        {"calibration_fraction": 0},
        {"train_fraction": 0.9, "calibration_fraction": 0.1},
        {"train_fraction": 0.95, "calibration_fraction": 0.2},
        {"min_events_per_set": 0},
        {"n_estimators": 0},
        {"max_samples": 0},
        {"max_samples": -5},
        {"max_samples": "many"},
        {"severity_medium": 0},
        {"severity_medium": 0.9, "severity_high": 0.8},
        {"severity_high": 1.1},
        {"anomaly_threshold": -0.1},
        {"anomaly_threshold": 1.5},
    ],
)
def test_invalid_policy_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MlPolicy.model_validate(kwargs)


def test_valid_custom_policy() -> None:
    p = MlPolicy(
        train_fraction=0.6,
        calibration_fraction=0.2,
        n_estimators=50,
        max_samples=256,
        severity_medium=0.5,
        severity_high=0.5,
    )
    assert (p.n_estimators, p.max_samples, p.severity_high) == (50, 256, 0.5)


def test_policy_errors_do_not_echo_the_value() -> None:
    with pytest.raises(ValidationError) as exc:
        MlPolicy.model_validate({"max_samples": "SENTINEL-VALUE"})
    assert "SENTINEL-VALUE" not in str(exc.value)


def test_score_has_no_probability_field() -> None:
    assert set(Score.model_fields) == {"raw_score", "anomaly_score", "severity", "is_anomaly"}
    assert not any("prob" in name for name in Score.model_fields)


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_anomaly_score_must_be_in_unit_interval(value: float) -> None:
    with pytest.raises(ValidationError):
        Score(raw_score=0.5, anomaly_score=value, severity="low", is_anomaly=False)


def test_severity_values_are_closed() -> None:
    with pytest.raises(ValidationError):
        Score(raw_score=0.5, anomaly_score=0.5, severity="critical", is_anomaly=False)  # type: ignore[arg-type]


def test_models_are_frozen() -> None:
    score = Score(raw_score=0.5, anomaly_score=0.5, severity="low", is_anomaly=False)
    with pytest.raises(ValidationError):
        score.severity = "high"


def _report(**changes: object) -> EvaluationReport:
    base: dict[str, object] = {
        "n_test": 100,
        "score_mean": 0.5,
        "score_quantiles": {"p0": 0.0, "p50": 0.5, "p100": 1.0},
        "alert_rate": 0.2,
        "temporal_stability": (StabilitySegment(index=0, n=25, mean_score=0.5, alert_rate=0.2),),
        "max_alert_rate_gap": 0.0,
        "incomplete_context": {"train": 1, "calibration": 0, "test": 0},
        "labelled": False,
        "classification": None,
        "limitations": ("datos sintéticos",),
    }
    base.update(changes)
    return EvaluationReport.model_validate(base)


def test_report_without_labels_has_no_classification() -> None:
    report = _report()
    assert report.labelled is False and report.classification is None


def test_report_with_labels_carries_the_metrics() -> None:
    metrics = ClassificationMetrics(
        calculable=True,
        precision=0.5,
        recall=1.0,
        f1=0.6667,
        pr_auc=0.8,
        confusion={"tp": 1, "fp": 1, "tn": 2, "fn": 0},
        reason=None,
    )
    assert _report(labelled=True, classification=metrics).classification == metrics


def test_a_non_calculable_classification_explains_why() -> None:
    metrics = ClassificationMetrics(
        calculable=False,
        precision=None,
        recall=None,
        f1=None,
        pr_auc=None,
        confusion={"tp": 0, "fp": 0, "tn": 4, "fn": 0},
        reason="sin positivos",
    )
    assert metrics.reason == "sin positivos"


def test_version_and_run_records() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    run_id = uuid.uuid4()
    version = ModelVersion(
        version="v0001",
        number=1,
        run_id=run_id,
        created_at=now,
        schema_version=1,
        schema_fingerprint="a" * 64,
        params={"n_estimators": 100},
        metrics={},
        dataset_hash="b" * 64,
        artifact_file="model-v0001.joblib",
        artifact_sha256="c" * 64,
        library_versions={"scikit-learn": "1.9.1"},
        active=False,
        activated_at=None,
    )
    assert version.active is False
    run = TrainingRun(
        id=run_id,
        status="running",
        started_at=now,
        heartbeat_at=now,
        finished_at=None,
        params={},
        dataset_hash=None,
        n_train=None,
        n_calibration=None,
        n_test=None,
        version=None,
        error_code=None,
    )
    assert run.status == "running"
    with pytest.raises(ValidationError):
        TrainingRun.model_validate({**run.model_dump(), "status": "paused"})
