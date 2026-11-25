"""Modelos del entrenamiento: política, puntuación, informe y registros (data-model.md).

``anomaly_score`` es un percentil frente a la distribución de calibración, nunca una probabilidad de
ataque (Principio II). Los modelos ocultan el valor de entrada en sus errores de validación.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from security_anomaly.schemas.storage import UtcDatetime

Severity = Literal["low", "medium", "high"]
RunStatus = Literal["running", "succeeded", "failed"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class MlPolicy(_Model):
    """Separación temporal, hiperparámetros, umbrales de severidad y umbral operativo."""

    train_fraction: float = Field(default=0.70, gt=0, lt=1)
    calibration_fraction: float = Field(default=0.15, gt=0, lt=1)
    min_events_per_set: int = Field(default=100, ge=1)
    n_estimators: int = Field(default=100, ge=1)
    max_samples: Annotated[int, Field(ge=1)] | Literal["auto"] = "auto"
    severity_medium: float = Field(default=0.80, gt=0, le=1)
    severity_high: float = Field(default=0.95, gt=0, le=1)
    anomaly_threshold: float = Field(default=0.80, ge=0, le=1)

    @model_validator(mode="after")
    def _coherent(self) -> "MlPolicy":
        if self.train_fraction + self.calibration_fraction >= 1:
            raise ValueError("entrenamiento y calibración no dejan datos para la prueba")
        if self.severity_medium > self.severity_high:
            raise ValueError("el umbral de medium no puede superar al de high")
        return self


class Score(_Model):
    """Resultado de puntuar un evento: bruta, percentil de calibración, severidad y bandera."""

    raw_score: float
    anomaly_score: float = Field(ge=0, le=1)
    severity: Severity
    is_anomaly: bool


class StabilitySegment(_Model):
    """Un tramo consecutivo del conjunto de prueba."""

    index: int = Field(ge=0)
    n: int = Field(ge=0)
    mean_score: float
    alert_rate: float = Field(ge=0, le=1)


class ClassificationMetrics(_Model):
    """Métricas con etiquetas sobre el conjunto de prueba; «no calculables» si falta una clase."""

    calculable: bool
    precision: float | None
    recall: float | None
    f1: float | None
    pr_auc: float | None
    confusion: dict[str, int]
    reason: str | None


class EvaluationReport(_Model):
    """Informe de evaluación con y sin etiquetas, con sus limitaciones."""

    n_test: int = Field(ge=0)
    score_mean: float
    score_quantiles: dict[str, float]
    alert_rate: float = Field(ge=0, le=1)
    temporal_stability: tuple[StabilitySegment, ...]
    max_alert_rate_gap: float = Field(ge=0)
    incomplete_context: dict[str, int]
    labelled: bool
    classification: ClassificationMetrics | None
    limitations: tuple[str, ...]


class ModelVersion(_Model):
    """Una versión de modelo registrada."""

    version: str
    number: int = Field(ge=1)
    run_id: UUID
    created_at: UtcDatetime
    schema_version: int = Field(ge=1)
    schema_fingerprint: str
    params: dict[str, object]
    metrics: dict[str, object]
    dataset_hash: str
    artifact_file: str
    artifact_sha256: str
    library_versions: dict[str, str]
    active: bool
    activated_at: UtcDatetime | None


class TrainingRun(_Model):
    """Una ejecución de entrenamiento registrada."""

    id: UUID
    status: RunStatus
    started_at: UtcDatetime
    heartbeat_at: UtcDatetime
    finished_at: UtcDatetime | None
    params: dict[str, object]
    dataset_hash: str | None
    n_train: int | None
    n_calibration: int | None
    n_test: int | None
    version: str | None
    error_code: str | None
