"""Clarificación 1, FR-003-12: empates de `timestamp` según `(timestamp, source, event_id)`."""

import random
from datetime import timedelta, timezone

from security_anomaly.features.engine import event_order_key
from tests.feature_factory import BASE, make_event, random_stream, run_engine

IP = "192.0.2.1"


def test_the_later_key_sees_the_earlier_one_but_not_the_other_way_round() -> None:
    first = make_event(0, event_id="a", timestamp=BASE, ip=IP)
    second = make_event(1, event_id="b", timestamp=BASE, ip=IP)
    result = run_engine([second, first])
    assert result[("linux-auth", "a")].ip_event_count == 1
    assert result[("linux-auth", "b")].ip_event_count == 2


def test_the_source_breaks_ties_before_the_event_id() -> None:
    low = make_event(0, event_id="z", source="a-src", timestamp=BASE, ip=IP)
    high = make_event(1, event_id="a", source="b-src", timestamp=BASE, ip=IP)
    result = run_engine([low, high])
    assert result[("a-src", "z")].ip_event_count == 1
    assert result[("b-src", "a")].ip_event_count == 1  # fuentes distintas no se suman


def test_ties_are_resolved_the_same_way_in_every_run_and_input_order() -> None:
    events = [make_event(i, event_id=f"t{i:02d}", timestamp=BASE, ip=IP) for i in range(12)]
    expected = {e.event_id: i + 1 for i, e in enumerate(events)}
    rng = random.Random(3)
    for _ in range(5):
        shuffled = list(events)
        rng.shuffle(shuffled)
        got = {k[1]: w.ip_event_count for k, w in run_engine(shuffled).items()}
        assert got == expected


def test_the_same_instant_in_two_time_zones_is_a_tie() -> None:
    plus2 = timezone(timedelta(hours=2))
    a = make_event(0, event_id="a", timestamp=BASE, ip=IP)
    b = make_event(1, event_id="b", timestamp=BASE.astimezone(plus2), ip=IP)
    assert event_order_key(a)[0] == event_order_key(b)[0]
    result = run_engine([b, a])
    assert (
        result[("linux-auth", "a")].ip_event_count,
        result[("linux-auth", "b")].ip_event_count,
    ) == (1, 2)


def test_streams_full_of_ties_are_independent_of_input_order() -> None:
    for seed in range(10):
        events = random_stream(seed, 80, span_seconds=30)
        shuffled = list(events)
        random.Random(seed).shuffle(shuffled)
        assert run_engine(events) == run_engine(shuffled)
