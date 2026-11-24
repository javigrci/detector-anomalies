"""FR-003-12: clave de orden total `(timestamp UTC, source, event_id)`."""

from datetime import UTC, datetime, timedelta, timezone

from security_anomaly.features.engine import event_order_key
from tests.feature_factory import make_event, make_stored

T0 = datetime(2026, 3, 1, 10, tzinfo=UTC)


def test_key_is_timestamp_in_utc_source_event_id() -> None:
    event = make_event(1, source="linux-auth", event_id="e1", timestamp=T0)
    assert event_order_key(event) == (T0, "linux-auth", "e1")


def test_same_instant_in_different_zones_ties_on_the_instant() -> None:
    plus2 = timezone(timedelta(hours=2))
    a = make_event(1, event_id="a", timestamp=T0)
    b = make_event(2, event_id="a", timestamp=T0.astimezone(plus2))
    assert event_order_key(a) == event_order_key(b)
    assert event_order_key(b)[0].utcoffset() == timedelta(0)


def test_ties_break_by_source_then_event_id() -> None:
    keys = [
        event_order_key(make_event(1, source="b-src", event_id="a", timestamp=T0)),
        event_order_key(make_event(2, source="a-src", event_id="z", timestamp=T0)),
        event_order_key(make_event(3, source="a-src", event_id="b", timestamp=T0)),
    ]
    assert sorted(keys) == [(T0, "a-src", "b"), (T0, "a-src", "z"), (T0, "b-src", "a")]


def test_earlier_instant_always_sorts_first() -> None:
    early = make_event(1, source="z-src", event_id="z", timestamp=T0)
    late = make_event(2, source="a-src", event_id="a", timestamp=T0 + timedelta(microseconds=1))
    assert event_order_key(early) < event_order_key(late)


def test_it_works_for_stored_events_too() -> None:
    stored = make_stored(1, source="linux-auth", event_id="e1", timestamp=T0)
    assert event_order_key(stored) == (T0, "linux-auth", "e1")
