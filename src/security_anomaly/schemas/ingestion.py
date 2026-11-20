"""Informe y resultado de una ingesta (FR-001-21).

Solo contienen códigos, nombres de campo, posiciones y recuentos; nunca valores de entrada.
"""

import json
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from security_anomaly.schemas.event import CATALOG_VERSION, NormalizedEvent

#: Máximo de entradas de rechazo por registro (una por campo con error).
MAX_REJECTIONS_PER_RECORD = 5


class RejectionCode(StrEnum):
    """Motivos de rechazo de un registro. Estables: añadir uno es un cambio de contrato."""

    MISSING_FIELD = "missing_field"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_TYPE = "invalid_type"
    INVALID_TIMESTAMP = "invalid_timestamp"
    TIMESTAMP_OUT_OF_RANGE = "timestamp_out_of_range"
    INVALID_IP = "invalid_ip"
    INVALID_OUTCOME = "invalid_outcome"
    INVALID_SOURCE = "invalid_source"
    FIELD_TOO_LONG = "field_too_long"
    INVALID_CHARACTERS = "invalid_characters"
    INVALID_RECORD = "invalid_record"
    MISSING_TIME_CONTEXT = "missing_time_context"


class BatchRejectionCode(StrEnum):
    """Motivos por los que se rechaza un archivo o lote completo."""

    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_EVENTS = "too_many_events"
    INVALID_ENCODING = "invalid_encoding"
    INVALID_FORMAT = "invalid_format"
    FILE_UNREADABLE = "file_unreadable"
    NOT_A_REGULAR_FILE = "not_a_regular_file"


class Rejection(BaseModel):
    """Un motivo de rechazo: posición (1-based), código y campo afectado (sin valores)."""

    model_config = ConfigDict(frozen=True)

    position: int = Field(ge=1)
    code: RejectionCode
    field: str | None = None


class Duplicate(BaseModel):
    """Duplicado omitido: posición y si su contenido difería de la primera aparición."""

    model_config = ConfigDict(frozen=True)

    position: int = Field(ge=1)
    content_differs: bool


class IngestionReport(BaseModel):
    """Resumen de una ingesta. Invariante: leídos = aceptados + rechazados + duplicados."""

    model_config = ConfigDict(frozen=True)

    catalog_version: int = CATALOG_VERSION
    total_records: int = Field(ge=0)
    accepted: int = Field(ge=0)
    rejected: int = Field(ge=0)
    rejections: tuple[Rejection, ...] = ()
    duplicates: tuple[Duplicate, ...] = ()
    out_of_order: tuple[int, ...] = ()
    ignored_lines: int = Field(default=0, ge=0)
    by_code: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.total_records != self.accepted + self.rejected + len(self.duplicates):
            raise ValueError("el total no coincide con aceptados + rechazados + duplicados")
        positions = [rejection.position for rejection in self.rejections]
        if self.rejected != len(set(positions)):
            raise ValueError("rechazados no coincide con las posiciones rechazadas")
        for position in set(positions):
            if positions.count(position) > MAX_REJECTIONS_PER_RECORD:
                raise ValueError("demasiadas entradas de rechazo para un mismo registro")
        return self


class IngestionResult(BaseModel):
    """Eventos válidos (en orden de lectura) y su informe."""

    model_config = ConfigDict(frozen=True)

    events: tuple[NormalizedEvent, ...]
    report: IngestionReport

    def to_canonical_json(self) -> str:
        """JSON con claves ordenadas, sin espacios y en UTF-8: idéntico para entradas idénticas."""
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
