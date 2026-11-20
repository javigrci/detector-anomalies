"""Validación y normalización de un registro (FR-001-01…05, 11…14, 16).

Los rechazos solo contienen código, campo y posición: nunca valores de entrada. El nombre de un
campo desconocido también es entrada no confiable, así que solo se informa si es un identificador
seguro; si no, se informa un marcador fijo (research R2).
"""

import ipaddress
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError

from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.event import Action, EventType, EventV1, NormalizedEvent, Outcome
from security_anomaly.schemas.ingestion import MAX_REJECTIONS_PER_RECORD, Rejection, RejectionCode

INVALID_NAME = "<invalid-name>"

_SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_SOURCE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_REQUIRED = frozenset({"event_id", "timestamp", "source", "event_type", "action", "outcome"})
_OPTIONAL = ("username", "source_ip", "host")
_FIELD_ORDER = (
    "event_id",
    "timestamp",
    "source",
    "event_type",
    "action",
    "outcome",
    "username",
    "source_ip",
    "host",
)


@dataclass(frozen=True)
class NormalizeResult:
    """Un evento normalizado o los motivos de rechazo (nunca ambos)."""

    event: NormalizedEvent | None
    rejections: tuple[Rejection, ...] = ()


def _clean(data: Mapping[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, str):
            value = unicodedata.normalize("NFC", value.strip())
            if value == "" and key in _OPTIONAL:
                value = None
        cleaned[str(key)] = value
    return cleaned


def _rejected(position: int, items: list[tuple[RejectionCode, str | None]]) -> NormalizeResult:
    return NormalizeResult(
        None,
        tuple(
            Rejection(position=position, code=code, field=field)
            for code, field in items[:MAX_REJECTIONS_PER_RECORD]
        ),
    )


def _structural(exc: ValidationError) -> list[tuple[RejectionCode, str | None]]:
    items: list[tuple[RejectionCode, str | None]] = []
    for error in exc.errors(include_input=False, include_url=False):
        name = str(error["loc"][0]) if error["loc"] else None
        kind = error["type"]
        if kind == "missing":
            items.append((RejectionCode.MISSING_FIELD, name))
        elif kind == "extra_forbidden":
            safe = name if name is not None and _SAFE_NAME.fullmatch(name) else INVALID_NAME
            items.append((RejectionCode.UNKNOWN_FIELD, safe))
        else:
            known = name if name in _FIELD_ORDER else None
            items.append((RejectionCode.INVALID_TYPE, known))
    return items


def _has_control_characters(value: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in value)


def _check_timestamp(
    value: str, policy: IngestionPolicy
) -> tuple[datetime | None, RejectionCode | None]:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, RejectionCode.INVALID_TIMESTAMP
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, RejectionCode.INVALID_TIMESTAMP
    try:
        if not policy.timestamp_min <= parsed < policy.timestamp_max:
            return None, RejectionCode.TIMESTAMP_OUT_OF_RANGE
        return parsed.astimezone(UTC), None
    except OverflowError:
        return None, RejectionCode.TIMESTAMP_OUT_OF_RANGE


def _semantic(
    event: EventV1, policy: IngestionPolicy
) -> tuple[list[tuple[RejectionCode, str | None]], datetime | None, Outcome | None, str | None]:
    problems: list[tuple[RejectionCode, str | None]] = []
    timestamp: datetime | None = None
    outcome: Outcome | None = None
    source_ip: str | None = None
    for field in _FIELD_ORDER:
        value = getattr(event, field)
        if value is None:
            continue
        if _has_control_characters(value):
            problems.append((RejectionCode.INVALID_CHARACTERS, field))
            continue
        if len(value) > policy.max_field_length:
            problems.append((RejectionCode.FIELD_TOO_LONG, field))
            continue
        if value == "" and field in _REQUIRED:
            problems.append((RejectionCode.MISSING_FIELD, field))
            continue
        if field == "source" and not _SOURCE.fullmatch(value.lower()):
            problems.append((RejectionCode.INVALID_SOURCE, field))
        elif field == "timestamp":
            timestamp, code = _check_timestamp(value, policy)
            if code is not None:
                problems.append((code, field))
        elif field == "outcome":
            try:
                outcome = Outcome(value.lower())
            except ValueError:
                problems.append((RejectionCode.INVALID_OUTCOME, field))
        elif field == "source_ip":
            try:
                if "%" in value:
                    raise ValueError
                source_ip = ipaddress.ip_address(value).compressed
            except ValueError:
                problems.append((RejectionCode.INVALID_IP, field))
    return problems, timestamp, outcome, source_ip


def normalize_record(
    data: Mapping[str, object] | None,
    *,
    position: int,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
) -> NormalizeResult:
    """Valida y normaliza un registro; ``None`` es un registro que no es un objeto."""
    if data is None:
        return _rejected(position, [(RejectionCode.INVALID_RECORD, None)])
    try:
        event = EventV1.model_validate(_clean(data))
    except ValidationError as exc:
        return _rejected(position, _structural(exc))

    problems, timestamp, outcome, source_ip = _semantic(event, policy)
    if problems or timestamp is None or outcome is None:
        return _rejected(position, problems or [(RejectionCode.INVALID_RECORD, None)])

    return NormalizeResult(
        NormalizedEvent(
            event_id=event.event_id,
            timestamp=timestamp,
            source=event.source.lower(),
            event_type=_catalog(EventType, event.event_type),
            action=_catalog(Action, event.action),
            outcome=outcome,
            user_pseudonym=(
                pseudonymizer.pseudonym(event.username) if event.username is not None else None
            ),
            source_ip=source_ip,
            host=event.host.lower() if event.host is not None else None,
            position=position,
        )
    )


def _catalog[E: (EventType, Action)](enum_cls: type[E], value: str) -> E:
    try:
        return enum_cls(value.lower())
    except ValueError:
        return enum_cls("other")
