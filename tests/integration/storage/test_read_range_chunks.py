"""FR-002-16: lectura por bloques sin duplicados ni saltos y con memoria acotada."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine

from security_anomaly.storage import read_range, save_events
from tests.storage_factory import BASE_TIME, make_event, make_events

pytestmark = pytest.mark.integration


def test_a_large_range_in_small_chunks_has_no_duplicates_or_gaps(app_engine: Engine) -> None:
    events = make_events(1234)
    save_events(app_engine, events)
    chunks = list(read_range(app_engine, BASE_TIME, BASE_TIME.replace(year=2027), chunk_size=100))
    assert max(len(c) for c in chunks) <= 100
    assert all(chunks)
    flat = [(e.timestamp, e.source, e.event_id) for chunk in chunks for e in chunk]
    assert len(flat) == len(set(flat)) == 1234
    assert flat == sorted(flat)
    assert {k[2] for k in flat} == {e.event_id for e in events}


def test_chunks_are_lazy(app_engine: Engine) -> None:
    save_events(app_engine, make_events(300))
    iterator = read_range(app_engine, BASE_TIME, BASE_TIME.replace(year=2027), chunk_size=50)
    first = next(iterator)
    assert len(first) == 50
    iterator.close()


def test_ties_across_a_chunk_boundary_are_not_lost_or_repeated(app_engine: Engine) -> None:
    same = datetime(2026, 5, 1, tzinfo=UTC)
    events = [make_event(i, event_id=f"tie-{i:03d}", timestamp=same) for i in range(25)]
    save_events(app_engine, events)
    flat = [
        e.event_id
        for chunk in read_range(app_engine, same, same.replace(day=2), chunk_size=10)
        for e in chunk
    ]
    assert flat == sorted(f"tie-{i:03d}" for i in range(25))


def test_inserting_between_chunks_does_not_duplicate_or_lose_the_ones_already_fixed(
    app_engine: Engine,
) -> None:
    save_events(app_engine, make_events(100, start=0))
    iterator = read_range(app_engine, BASE_TIME, BASE_TIME.replace(year=2027), chunk_size=30)
    first = next(iterator)
    # Llegan eventos anteriores y posteriores al último leído mientras se recorre.
    save_events(app_engine, make_events(10, start=1000))
    save_events(app_engine, [make_event(-1, event_id="before-everything", timestamp=BASE_TIME)])
    rest = [event for chunk in iterator for event in chunk]
    ids = [e.event_id for e in first] + [e.event_id for e in rest]
    assert len(ids) == len(set(ids))
    assert {f"evt-{i:06d}" for i in range(100)} <= set(ids)
