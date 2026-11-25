"""FR-004-14, 29: configuración del entrenamiento desde el entorno."""

from pathlib import Path

import pytest

from security_anomaly.core.config import ConfigError
from security_anomaly.ml.config import load_ml_settings


def test_defaults_and_policy(tmp_path: Path) -> None:
    settings = load_ml_settings({"MODEL_DIR": str(tmp_path)})
    assert settings.model_dir == tmp_path
    p = settings.policy
    assert (p.train_fraction, p.calibration_fraction, p.min_events_per_set) == (0.70, 0.15, 100)
    assert (p.severity_medium, p.severity_high, p.anomaly_threshold) == (0.80, 0.95, 0.80)
    assert p.n_estimators == 100
    assert settings.stale_minutes == 60


def test_every_variable_is_read(tmp_path: Path) -> None:
    settings = load_ml_settings(
        {
            "MODEL_DIR": str(tmp_path),
            "SEVERITY_MEDIUM": "0.6",
            "SEVERITY_HIGH": "0.9",
            "ANOMALY_THRESHOLD": "0.7",
            "TRAIN_FRACTION": "0.6",
            "CALIBRATION_FRACTION": "0.2",
            "MIN_EVENTS_PER_SET": "50",
            "IFOREST_N_ESTIMATORS": "25",
            "TRAINING_STALE_MINUTES": "5",
        }
    )
    p = settings.policy
    assert (p.severity_medium, p.severity_high, p.anomaly_threshold) == (0.6, 0.9, 0.7)
    assert (p.train_fraction, p.calibration_fraction, p.min_events_per_set) == (0.6, 0.2, 50)
    assert p.n_estimators == 25 and settings.stale_minutes == 5


def test_blank_values_are_absent(tmp_path: Path) -> None:
    settings = load_ml_settings({"MODEL_DIR": str(tmp_path), "SEVERITY_HIGH": "  "})
    assert settings.policy.severity_high == 0.95


def test_model_dir_is_required() -> None:
    with pytest.raises(ConfigError) as exc:
        load_ml_settings({})
    assert "MODEL_DIR" in str(exc.value)


@pytest.mark.parametrize("value", ["relativo/modelos", "~/modelos", "../modelos"])
def test_model_dir_must_be_absolute(value: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_ml_settings({"MODEL_DIR": value})
    assert "MODEL_DIR" in str(exc.value)
    assert value not in str(exc.value)


def test_model_dir_must_exist_and_be_a_directory(tmp_path: Path) -> None:
    missing = tmp_path / "no-existe"
    with pytest.raises(ConfigError) as exc:
        load_ml_settings({"MODEL_DIR": str(missing)})
    assert str(missing) not in str(exc.value)
    a_file = tmp_path / "archivo"
    a_file.write_text("x")
    with pytest.raises(ConfigError):
        load_ml_settings({"MODEL_DIR": str(a_file)})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SEVERITY_MEDIUM", "0"),
        ("SEVERITY_HIGH", "1.5"),
        ("ANOMALY_THRESHOLD", "-1"),
        ("TRAIN_FRACTION", "0"),
        ("CALIBRATION_FRACTION", "abc"),
        ("MIN_EVENTS_PER_SET", "0"),
        ("IFOREST_N_ESTIMATORS", "0"),
        ("TRAINING_STALE_MINUTES", "0"),
    ],
)
def test_invalid_values_name_the_variable_not_the_value(
    tmp_path: Path, name: str, value: str
) -> None:
    with pytest.raises(ConfigError) as exc:
        load_ml_settings({"MODEL_DIR": str(tmp_path), name: value})
    assert name in str(exc.value)
    assert value not in str(exc.value) or value in {"0", "1.5", "-1"}


def test_incoherent_thresholds_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_ml_settings(
            {"MODEL_DIR": str(tmp_path), "SEVERITY_MEDIUM": "0.9", "SEVERITY_HIGH": "0.8"}
        )
