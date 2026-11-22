"""FR-002-03, 14, SC-003: paginación estable con total."""

import pytest
from sqlalchemy import Engine

from security_anomaly.schemas.storage import EventFilter
from security_anomaly.storage import query_events, save_events
from tests.storage_factory import make_events

pytestmark = pytest.mark.integration


def _walk(engine: Engine, page_size: int) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    offset = 0
    while True:
        page = query_events(engine, EventFilter(), limit=page_size, offset=offset)
        seen.extend((e.source, e.event_id) for e in page.items)
        offset += page_size
        if offset >= page.total:
            return seen


def test_five_thousand_events_in_pages_of_one_hundred(app_engine: Engine) -> None:
    save_events(app_engine, make_events(5000))
    first = _walk(app_engine, 100)
    second = _walk(app_engine, 100)
    assert len(first) == 5000
    assert len(set(first)) == 5000
    assert first == second
    assert first == sorted(first, key=lambda key: (key[1], key[0]))  # timestamps crecientes = ids


def test_page_reports_total_limit_and_offset(app_engine: Engine) -> None:
    save_events(app_engine, make_events(25))
    page = query_events(app_engine, limit=10, offset=20)
    assert (page.total, page.limit, page.offset, len(page.items)) == (25, 10, 20, 5)


def test_default_limit_and_total_under_filters(app_engine: Engine) -> None:
    save_events(app_engine, make_events(150))
    page = query_events(app_engine)
    assert (page.total, page.limit, len(page.items)) == (150, 100, 100)


def test_ties_in_timestamp_have_a_stable_order(app_engine: Engine) -> None:
    from datetime import UTC, datetime

    from tests.storage_factory import make_event

    when = datetime(2026, 3, 1, tzinfo=UTC)
    events = [make_event(i, event_id=f"tie-{i:03d}", timestamp=when) for i in range(30)]
    save_events(app_engine, list(reversed(events)))
    orders = [[e.event_id for e in query_events(app_engine, limit=30).items] for _ in range(3)]
    assert orders[0] == orders[1] == orders[2] == sorted(f"tie-{i:03d}" for i in range(30))


def test_offset_beyond_the_end_is_an_empty_page(app_engine: Engine) -> None:
    save_events(app_engine, make_events(5))
    page = query_events(app_engine, limit=10, offset=100)
    assert (page.items, page.total) == ((), 5)
