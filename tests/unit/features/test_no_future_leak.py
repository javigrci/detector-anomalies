"""SC-001 y Principio III: ninguna modificación del futuro cambia un vector (puerta del roadmap)."""

import random
from datetime import timedelta
from typing import Any

import pytest

from security_anomaly.features.engine import event_order_key
from security_anomaly.schemas.event import NormalizedEvent, Outcome
from tests.feature_factory import (
    BASE,
    make_event,
    pseudonym,
    random_stream,
    run_engine,
)

SEEDS = range(50)


def _frozen(events: list[NormalizedEvent], limit: Any) -> dict[tuple[str, str], Any]:
    """Agregadas de los eventos con clave <= `limit`, calculadas con el conjunto dado."""
    result = run_engine(events)
    return {
        (e.source, e.event_id): result[(e.source, e.event_id)]
        for e in events
        if event_order_key(e) <= limit
    }


def _mutations(
    rng: random.Random, events: list[NormalizedEvent], target: NormalizedEvent
) -> dict[str, list[NormalizedEvent]]:
    limit = event_order_key(target)
    past = [e for e in events if event_order_key(e) <= limit]
    future = [e for e in events if event_order_key(e) > limit]
    ips = ["192.0.2.1", "192.0.2.2", "2001:db8::1", None]
    extra = [
        make_event(
            1000 + i,
            event_id=f"zz-new-{i}",
            source=target.source,
            timestamp=target.timestamp + timedelta(seconds=rng.randrange(0, 200)),
            outcome=rng.choice([Outcome.FAILURE, Outcome.SUCCESS]),
            user=pseudonym(rng.randrange(8)),
            ip=rng.choice(ips),
        )
        for i in range(10)
    ]
    # Todos los añadidos van **después** del objetivo en el orden total (id mayor en el empate).
    extra = [e for e in extra if event_order_key(e) > limit]
    modified = [
        e.model_copy(
            update={
                "source_ip": rng.choice(ips),
                "user_pseudonym": pseudonym(rng.randrange(8)),
                "outcome": rng.choice([Outcome.FAILURE, Outcome.SUCCESS]),
                "timestamp": e.timestamp + timedelta(seconds=rng.randrange(1, 90)),
            }
        )
        for e in future
    ]
    return {
        "removed": past,
        "added": [*past, *future, *extra],
        "modified": [*past, *modified],
        "removed_half": [*past, *future[::2]],
    }


@pytest.mark.parametrize("seed", SEEDS)
def test_changing_the_future_never_changes_a_vector(seed: int) -> None:
    rng = random.Random(seed)
    events = random_stream(seed, 70, span_seconds=420)
    ordered = sorted(events, key=event_order_key)
    for target in rng.sample(ordered, 4):
        limit = event_order_key(target)
        baseline = _frozen(events, limit)
        for name, variant in _mutations(rng, events, target).items():
            assert _frozen(variant, limit) == baseline, (seed, name, target.event_id)


def test_a_burst_followed_by_a_flood_changes_nothing_in_the_past() -> None:
    ip = "198.51.100.7"
    burst = [
        make_event(
            i,
            event_id=f"b{i:02d}",
            timestamp=BASE + timedelta(seconds=i),
            outcome=Outcome.FAILURE,
            ip=ip,
        )
        for i in range(10)
    ]
    flood = [
        make_event(
            100 + i,
            event_id=f"f{i:03d}",
            timestamp=BASE + timedelta(seconds=10 + i // 4),
            outcome=Outcome.FAILURE,
            ip=ip,
        )
        for i in range(200)
    ]
    limit = event_order_key(burst[-1])
    assert _frozen(burst, limit) == _frozen([*burst, *flood], limit)
    last = run_engine(burst)[("linux-auth", "b09")]
    assert (last.ip_event_count, last.ip_failure_count) == (10, 10)
