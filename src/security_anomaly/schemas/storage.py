"""Modelos de la persistencia: filtros, eventos almacenados, páginas y resúmenes.

Ver specs/002-persistence/data-model.md. Los modelos ocultan el valor de entrada en sus errores de
validación: un filtro con un nombre de usuario real no debe volver a aparecer en un mensaje.
"""

import ipaddress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from security_anomaly.schemas.event import Action, EventType, Outcome

SOURCE_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
PSEUDONYM_PATTERN = r"^usr_[0-9a-f]{32}$"


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class EventFilter(_Model):
    """Filtros combinables por conjunción; ``[date_from, date_to)``."""

    date_from: UtcDatetime | None = None
    date_to: UtcDatetime | None = None
    source: Annotated[str, Field(pattern=SOURCE_PATTERN)] | None = None
    event_type: EventType | None = None
    action: Action | None = None
    outcome: Outcome | None = None
    source_ip: str | None = None
    user_pseudonym: Annotated[str, Field(pattern=PSEUDONYM_PATTERN)] | None = None

    @field_validator("source_ip")
    @classmethod
    def _normalize_ip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "%" in value:
            raise ValueError("dirección IP inválida")
        try:
            return ipaddress.ip_address(value).compressed
        except ValueError:
            raise ValueError("dirección IP inválida") from None

    @model_validator(mode="after")
    def _date_order(self) -> "EventFilter":
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from >= self.date_to
        ):
            raise ValueError("date_from debe ser anterior a date_to")
        return self


class StoredEvent(_Model):
    """Evento persistido; nunca contiene el nombre de usuario original."""

    source: str
    event_id: str
    timestamp: UtcDatetime
    event_type: EventType
    action: Action
    outcome: Outcome
    user_pseudonym: str | None = None
    source_ip: str | None = None
    host: str | None = None
    ingested_at: UtcDatetime
    batch_id: UUID


class EventPage(_Model):
    items: tuple[StoredEvent, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class SaveSummary(_Model):
    """``inserted + existing`` es el número de eventos distintos de la entrada."""

    batch_id: UUID
    inserted: int = Field(ge=0)
    existing: int = Field(ge=0)
    existing_with_different_content: int = Field(ge=0)

    @model_validator(mode="after")
    def _different_within_existing(self) -> "SaveSummary":
        if self.existing_with_different_content > self.existing:
            raise ValueError("existing_with_different_content supera a existing")
        return self


class PurgeResult(_Model):
    retention_days: int = Field(ge=1)
    cutoff: UtcDatetime
    dry_run: bool
    affected: int = Field(ge=0)
