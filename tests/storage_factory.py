"""Generador de eventos ficticios y deterministas para los tests de la persistencia."""

import hashlib
from datetime import UTC, datetime, timedelta

from security_anomaly.schemas.event import Action, EventType, NormalizedEvent, Outcome

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def pseudonym_for(n: int) -> str:
    """Seudónimo ficticio con el formato `usr_<32 hex>` (no es un HMAC real)."""
    return "usr_" + hashlib.sha256(f"user{n:03d}".encode()).hexdigest()[:32]


def make_event(
    index: int,
    *,
    source: str = "linux-auth",
    event_id: str | None = None,
    timestamp: datetime | None = None,
    outcome: Outcome = Outcome.SUCCESS,
    action: Action = Action.LOGIN,
    event_type: EventType = EventType.AUTHENTICATION,
    user_pseudonym: str | None = None,
    source_ip: str | None = None,
    host: str | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id if event_id is not None else f"evt-{index:06d}",
        timestamp=timestamp if timestamp is not None else BASE_TIME + timedelta(seconds=index),
        source=source,
        event_type=event_type,
        action=action,
        outcome=outcome,
        user_pseudonym=user_pseudonym if user_pseudonym is not None else pseudonym_for(index % 20),
        source_ip=source_ip if source_ip is not None else f"192.0.2.{index % 250 + 1}",
        host=host if host is not None else f"srv-demo-{index % 10:02d}",
        position=index,
    )


def make_events(
    count: int,
    *,
    start: int = 0,
    source: str = "linux-auth",
    step: timedelta = timedelta(seconds=1),
    first: datetime = BASE_TIME,
) -> list[NormalizedEvent]:
    """`count` eventos con identificadores `evt-<n>` y timestamps crecientes."""
    return [
        make_event(i, source=source, timestamp=first + step * i)
        for i in range(start, start + count)
    ]
