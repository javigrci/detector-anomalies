"""Ayudas de test de las características: eventos ficticios, flujos reproducibles y un oráculo.

El oráculo (`reference_*`) es una implementación lenta, O(n²), escrita directamente de las
definiciones de `contracts/feature-schema.md` y sin usar el código de producción: sirve para
comprobar el motor. Solo datos ficticios (IPs de documentación, `userNNN`, `srv-demo`).
"""

import hashlib
import ipaddress
import math
import random
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from security_anomaly.schemas.event import Action, EventType, NormalizedEvent, Outcome
from security_anomaly.schemas.storage import StoredEvent

BASE = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=5)
_ZONES = (UTC, timezone(timedelta(hours=2)), timezone(timedelta(hours=-5)))


def pseudonym(n: int) -> str:
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
    user: str | None = None,
    ip: str | None = None,
    host: str | None = "srv-demo-01",
) -> NormalizedEvent:
    """Evento normalizado; `user` e `ip` son seudónimo e IP tal cual (None = ausente)."""
    return NormalizedEvent(
        event_id=event_id if event_id is not None else f"evt-{index:06d}",
        timestamp=timestamp if timestamp is not None else BASE + timedelta(seconds=index),
        source=source,
        event_type=event_type,
        action=action,
        outcome=outcome,
        user_pseudonym=user,
        source_ip=ip,
        host=host,
        position=index + 1,
    )


def make_stored(index: int, **kwargs: Any) -> StoredEvent:
    """Evento almacenado equivalente (con `ingested_at` y `batch_id` ficticios)."""
    event = make_event(index, **kwargs)
    return StoredEvent(
        source=event.source,
        event_id=event.event_id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        action=event.action,
        outcome=event.outcome,
        user_pseudonym=event.user_pseudonym,
        source_ip=event.source_ip,
        host=event.host,
        ingested_at=BASE,
        batch_id=uuid.UUID(int=index),
    )


_IPS = [
    "192.0.2.1",
    "192.0.2.2",
    "198.51.100.7",
    "198.51.100.8",
    "203.0.113.9",
    "2001:db8::1",
    "2001:db8::2",
    "2001:db8:0:1::5",
]


def random_stream(
    seed: int,
    n: int,
    *,
    sources: Sequence[str] = ("linux-auth",),
    n_users: int = 6,
    span_seconds: int = 1500,
    no_ip_rate: float = 0.1,
    no_user_rate: float = 0.1,
    failure_rate: float = 0.5,
    mixed_zones: bool = True,
) -> list[NormalizedEvent]:
    """Flujo reproducible con muchos empates de `timestamp`; sin ordenar por instante."""
    rng = random.Random(seed)
    events: list[NormalizedEvent] = []
    for i in range(n):
        seconds = rng.randrange(span_seconds)
        zone = _ZONES[rng.randrange(len(_ZONES))] if mixed_zones else UTC
        events.append(
            make_event(
                i,
                source=sources[rng.randrange(len(sources))],
                event_id=f"e{rng.randrange(10**9):09d}-{i}",
                timestamp=(BASE + timedelta(seconds=seconds)).astimezone(zone),
                outcome=Outcome.FAILURE if rng.random() < failure_rate else Outcome.SUCCESS,
                user=None if rng.random() < no_user_rate else pseudonym(rng.randrange(n_users)),
                ip=None if rng.random() < no_ip_rate else _IPS[rng.randrange(len(_IPS))],
                host=f"srv-demo-{rng.randrange(3):02d}",
            )
        )
    return events


# --- Oráculo de referencia (independiente del código de producción) -------------------------


def _key(event: Any) -> tuple[datetime, str, str]:
    return (event.timestamp.astimezone(UTC), event.source, event.event_id)


def _ip(value: str | None) -> str | None:
    return None if value is None else ipaddress.ip_address(value).compressed


def reference_window(events: Sequence[Any], target: Any) -> dict[str, float | int]:
    """Las cinco agregadas de `target` calculadas por fuerza bruta desde la definición."""
    t = target.timestamp.astimezone(UTC)
    context = [
        e
        for e in events
        if e.source == target.source
        and _key(e) <= _key(target)
        and e.timestamp.astimezone(UTC) > t - WINDOW
    ]
    result: dict[str, float | int] = {
        "ip_event_count": 0,
        "ip_failure_count": 0,
        "ip_failure_rate": 0.0,
        "ip_distinct_users": 0,
        "user_distinct_ips": 0,
    }
    ip = _ip(target.source_ip)
    if ip is not None:
        same_ip = [e for e in context if _ip(e.source_ip) == ip]
        failures = sum(1 for e in same_ip if e.outcome == Outcome.FAILURE)
        result["ip_event_count"] = len(same_ip)
        result["ip_failure_count"] = failures
        result["ip_failure_rate"] = failures / len(same_ip)
        result["ip_distinct_users"] = len({e.user_pseudonym for e in same_ip if e.user_pseudonym})
    if target.user_pseudonym is not None:
        result["user_distinct_ips"] = len(
            {
                _ip(e.source_ip)
                for e in context
                if e.user_pseudonym == target.user_pseudonym and e.source_ip is not None
            }
        )
    return result


def reference_event_level(event: Any) -> dict[str, float | int | str]:
    t = event.timestamp.astimezone(UTC)
    angle = 2 * math.pi * t.hour / 24
    return {
        "hour_sin": round(math.sin(angle), 12),
        "hour_cos": round(math.cos(angle), 12),
        "day_of_week": t.weekday(),
        "event_type": str(event.event_type.value),
        "action": str(event.action.value),
        "outcome": str(event.outcome.value),
        "source": event.source,
    }


def reference_features(
    events: Sequence[Any], target: Any, history_start: datetime
) -> tuple[dict[str, float | int | str], bool]:
    """Características y `context_complete` de `target` según el contrato del esquema v1."""
    features: dict[str, float | int | str] = {
        **reference_event_level(target),
        **reference_window(events, target),
        "has_ip": 0 if target.source_ip is None else 1,
        "has_user": 0 if target.user_pseudonym is None else 1,
    }
    complete = target.timestamp.astimezone(UTC) - WINDOW >= history_start
    return features, complete


def run_engine(events: Sequence[Any]) -> dict[tuple[str, str], Any]:
    """Pasa los eventos por el motor en orden total y devuelve sus agregadas por `(source, id)`."""
    from security_anomaly.features.engine import FeatureEngine, event_order_key

    engine = FeatureEngine()
    return {(e.source, e.event_id): engine.observe(e) for e in sorted(events, key=event_order_key)}
