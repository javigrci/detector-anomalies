"""Eventos de seguridad: esquema de entrada v1, catálogo canónico y evento normalizado.

Ver SPEC §4.1 y specs/001-ingestion/data-model.md.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

#: Versión del catálogo canónico; cambiar el catálogo exige subirla.
CATALOG_VERSION = 1


class EventType(StrEnum):
    AUTHENTICATION = "authentication"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    OTHER = "other"


class Action(StrEnum):
    LOGIN = "login"
    INVALID_USER = "invalid_user"
    SUDO = "sudo"
    OTHER = "other"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class EventV1(BaseModel):
    """Evento de entrada tal como llega (todo texto); el normalizador lo valida y convierte.

    Un campo desconocido provoca un error de validación (``extra_forbidden``), que la ingesta
    traduce en el rechazo ``unknown_field``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: str
    timestamp: str
    source: str
    event_type: str
    action: str
    outcome: str
    username: str | None = None
    source_ip: str | None = None
    host: str | None = None


class NormalizedEvent(BaseModel):
    """Evento validado y normalizado. Nunca contiene el nombre de usuario original."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    timestamp: datetime
    source: str
    event_type: EventType
    action: Action
    outcome: Outcome
    user_pseudonym: str | None = None
    source_ip: str | None = None
    host: str | None = None
    out_of_order: bool = False
    position: int
