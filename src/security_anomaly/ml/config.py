"""Configuración del entrenamiento desde el entorno (contracts/environment.md; FR-004-14, 29).

Los errores nombran la variable y nunca su valor.
"""

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from security_anomaly.core.config import load_model
from security_anomaly.schemas.ml import MlPolicy

ENV_VARS: dict[str, str] = {
    "model_dir": "MODEL_DIR",
    "severity_medium": "SEVERITY_MEDIUM",
    "severity_high": "SEVERITY_HIGH",
    "anomaly_threshold": "ANOMALY_THRESHOLD",
    "train_fraction": "TRAIN_FRACTION",
    "calibration_fraction": "CALIBRATION_FRACTION",
    "min_events_per_set": "MIN_EVENTS_PER_SET",
    "n_estimators": "IFOREST_N_ESTIMATORS",
    "stale_minutes": "TRAINING_STALE_MINUTES",
}


class MlSettings(BaseModel):
    """Directorio de confianza de los artefactos, política de entrenamiento y caducidad."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    model_dir: Path
    severity_medium: float = 0.80
    severity_high: float = 0.95
    anomaly_threshold: float = 0.80
    train_fraction: float = 0.70
    calibration_fraction: float = 0.15
    min_events_per_set: int = 100
    n_estimators: int = 100
    stale_minutes: int = Field(default=60, ge=1)

    @field_validator("model_dir")
    @classmethod
    def _trusted_directory(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("debe ser una ruta absoluta")
        if not value.is_dir():
            raise ValueError("debe ser un directorio existente")
        return value

    @model_validator(mode="after")
    def _valid_policy(self) -> "MlSettings":
        self.policy  # noqa: B018 - valida la coherencia de la política al cargar
        return self

    @property
    def policy(self) -> MlPolicy:
        return MlPolicy(
            train_fraction=self.train_fraction,
            calibration_fraction=self.calibration_fraction,
            min_events_per_set=self.min_events_per_set,
            n_estimators=self.n_estimators,
            severity_medium=self.severity_medium,
            severity_high=self.severity_high,
            anomaly_threshold=self.anomaly_threshold,
        )


def load_ml_settings(environ: Mapping[str, str] | None = None) -> MlSettings:
    return load_model(MlSettings, ENV_VARS, environ)
