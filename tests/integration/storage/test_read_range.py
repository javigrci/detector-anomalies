"""FR-002-16, Principio III: lectura por rango semiabierto sin fuga de futuro."""

from datetime import timedelta

import pytest
from sqlalchemy import Engine

from security_anomaly.storage import read_range, save_events
from tests.storage_factory import BASE_TIME, make_event

pytestmark = pytest.mark.integration


def _read(engine: Engine, start, end, **kw):  # type: ignore[no-untyped-def]
    return [event for chunk in read_range(engine, start, end, **kw) for event in chunk]


def _hour(n: int):  # type: ignore[no-untyped-def]
    return BASE_TIME + timedelta(hours=n)


def test_events_come_in_chronological_order_with_a_stable_tiebreak(app_engine: Engine) -> None:
    events = [
        make_event(1, event_id="b", timestamp=_hour(2)),
        make_event(2, event_id="a", timestamp=_hour(2)),
        make_event(3, event_id="z", timestamp=_hour(1)),
        make_event(4, event_id="a", source="aaa-src", timestamp=_hour(2)),
    ]
    save_events(app_engine, events)
    got = _read(app_engine, _hour(0), _hour(5))
    assert [(e.timestamp, e.source, e.event_id) for e in got] == [
        (_hour(1), "linux-auth", "z"),
        (_hour(2), "aaa-src", "a"),
        (_hour(2), "linux-auth", "a"),
        (_hour(2), "linux-auth", "b"),
    ]
    assert got == _read(app_engine, _hour(0), _hour(5))


def test_the_end_of_the_range_is_exclusive_and_the_start_inclusive(app_engine: Engine) -> None:
    save_events(app_engine, [make_event(i, event_id=f"h{i}", timestamp=_hour(i)) for i in range(6)])
    got = _read(app_engine, _hour(1), _hour(4))
    assert [e.event_id for e in got] == ["h1", "h2", "h3"]
    assert all(_hour(1) <= e.timestamp < _hour(4) for e in got)


def test_a_window_that_ends_exactly_at_an_event_never_returns_it(app_engine: Engine) -> None:
    save_events(app_engine, [make_event(0, event_id="edge", timestamp=_hour(3))])
    assert _read(app_engine, _hour(0), _hour(3)) == []
    assert [e.event_id for e in _read(app_engine, _hour(3), _hour(4))] == ["edge"]


def test_no_future_leak_with_tiny_chunks(app_engine: Engine) -> None:
    events = [make_event(i, event_id=f"e{i:03d}", timestamp=_hour(i % 10)) for i in range(100)]
    save_events(app_engine, events)
    end = _hour(5)
    got = _read(app_engine, _hour(0), end, chunk_size=7)
    assert got and all(e.timestamp < end for e in got)
    assert len(got) == 50


def test_events_saved_out_of_order_or_in_other_batches_sort_by_timestamp(
    app_engine: Engine,
) -> None:
    save_events(app_engine, [make_event(1, event_id="late", timestamp=_hour(9))])
    save_events(app_engine, [make_event(2, event_id="early", timestamp=_hour(1))])
    save_events(app_engine, [make_event(3, event_id="middle", timestamp=_hour(5))])
    got = _read(app_engine, _hour(0), _hour(10))
    assert [e.event_id for e in got] == ["early", "middle", "late"]


def test_an_empty_range_yields_nothing(app_engine: Engine) -> None:
    assert _read(app_engine, _hour(0), _hour(1)) == []
