"""Política de ingesta: límites configurables y rango de fechas válido (FR-001-17)."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from security_anomaly.core.config import load_model

ENV_VARS: dict[str, str] = {
    "max_file_bytes": "INGEST_MAX_FILE_BYTES",
    "max_events_per_batch": "INGEST_MAX_EVENTS_PER_BATCH",
    "max_events_per_dataset": "INGEST_MAX_EVENTS_PER_DATASET",
    "max_field_length": "INGEST_MAX_FIELD_LENGTH",
    "timestamp_min": "INGEST_TIMESTAMP_MIN",
    "timestamp_max": "INGEST_TIMESTAMP_MAX",
}


class IngestionPolicy(BaseModel):
    """Límites y rango de fechas con los valores iniciales de SPEC §4.3."""

    model_config = ConfigDict(frozen=True)

    max_file_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_events_per_batch: int = Field(default=10_000, gt=0)
    max_events_per_dataset: int = Field(default=100_000, gt=0)
    max_field_length: int = Field(default=256, gt=0)
    timestamp_min: datetime = datetime(2000, 1, 1, tzinfo=UTC)
    timestamp_max: datetime = datetime(2100, 1, 1, tzinfo=UTC)

    @field_validator("timestamp_min", "timestamp_max")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("se requiere zona horaria")
        return value

    @field_validator("timestamp_max")
    @classmethod
    def _ordered_range(cls, value: datetime, info: ValidationInfo) -> datetime:
        minimum = info.data.get("timestamp_min")
        if isinstance(minimum, datetime) and value <= minimum:
            raise ValueError("el rango de fechas no es válido")
        return value

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Carga la política de las variables ``INGEST_*``; vacío = valor por defecto."""
        return load_model(cls, ENV_VARS, environ)
