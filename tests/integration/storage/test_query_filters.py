"""FR-002-13, 17: filtros por separado y combinados sobre PostgreSQL real."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine

from security_anomaly.schemas.event import Action, EventType, Outcome
from security_anomaly.schemas.storage import EventFilter
from security_anomaly.storage import query_events, save_events
from tests.storage_factory import BASE_TIME, make_event, pseudonym_for

pytestmark = pytest.mark.integration

U1, U2 = pseudonym_for(1), pseudonym_for(2)


@pytest.fixture
def loaded(app_engine: Engine) -> Engine:
    events = [
        make_event(0, event_id="a", timestamp=BASE_TIME, user_pseudonym=U1, source_ip="192.0.2.1"),
        make_event(
            1,
            event_id="b",
            timestamp=BASE_TIME + timedelta(hours=1),
            outcome=Outcome.FAILURE,
            user_pseudonym=U1,
            source_ip="2001:db8::1",
        ),
        make_event(
            2,
            event_id="c",
            timestamp=BASE_TIME + timedelta(hours=2),
            action=Action.SUDO,
            event_type=EventType.PRIVILEGE_ESCALATION,
            user_pseudonym=U2,
            source_ip="192.0.2.2",
        ),
        make_event(
            3,
            event_id="d",
            source="other-src",
            timestamp=BASE_TIME + timedelta(hours=3),
            outcome=Outcome.FAILURE,
            user_pseudonym=U2,
            source_ip="192.0.2.1",
        ),
        make_event(4, event_id="e", timestamp=BASE_TIME + timedelta(hours=4)).model_copy(
            update={"user_pseudonym": None, "source_ip": None, "host": None}
        ),
    ]
    save_events(app_engine, events)
    return app_engine


def _ids(engine: Engine, **kwargs: object) -> list[str]:
    page = query_events(engine, EventFilter.model_validate(kwargs))
    return [e.event_id for e in page.items]


def test_no_filter_returns_everything_in_total_order(loaded: Engine) -> None:
    assert _ids(loaded) == ["a", "b", "c", "d", "e"]


def test_date_range_is_half_open(loaded: Engine) -> None:
    one = BASE_TIME + timedelta(hours=1)
    three = BASE_TIME + timedelta(hours=3)
    assert _ids(loaded, date_from=one, date_to=three) == ["b", "c"]
    assert _ids(loaded, date_from=three) == ["d", "e"]
    assert _ids(loaded, date_to=one) == ["a"]


def test_each_catalog_filter(loaded: Engine) -> None:
    assert _ids(loaded, source="other-src") == ["d"]
    assert _ids(loaded, event_type="privilege_escalation") == ["c"]
    assert _ids(loaded, action="sudo") == ["c"]
    assert _ids(loaded, outcome="failure") == ["b", "d"]


def test_filters_are_combined_with_and(loaded: Engine) -> None:
    assert _ids(loaded, outcome="failure", source="linux-auth") == ["b"]
    assert _ids(loaded, outcome="failure", user_pseudonym=U2) == ["d"]
    assert _ids(loaded, source_ip="192.0.2.1", outcome="success") == ["a"]


def test_ip_filter_treats_equivalent_spellings_as_equal(loaded: Engine) -> None:
    expected = ["b"]
    assert _ids(loaded, source_ip="2001:db8::1") == expected
    assert _ids(loaded, source_ip="2001:0db8:0000:0000:0000:0000:0000:0001") == expected
    assert _ids(loaded, source_ip="192.0.2.1") == ["a", "d"]


def test_pseudonym_filter(loaded: Engine) -> None:
    assert _ids(loaded, user_pseudonym=U1) == ["a", "b"]
    assert _ids(loaded, user_pseudonym=pseudonym_for(99)) == []


def test_null_fields_do_not_break_filters_or_order(loaded: Engine) -> None:
    page = query_events(loaded)
    last = page.items[-1]
    assert (last.user_pseudonym, last.source_ip, last.host) == (None, None, None)
    assert "e" not in _ids(loaded, source_ip="192.0.2.1")
    assert "e" not in _ids(loaded, user_pseudonym=U1)


def test_empty_result_is_an_empty_page_with_total_zero(loaded: Engine) -> None:
    page = query_events(loaded, EventFilter(source="no-such-source"))
    assert (page.items, page.total, page.offset) == ((), 0, 0)
    assert page.limit == 100


def test_returned_values_are_normalized(loaded: Engine) -> None:
    event = query_events(loaded, EventFilter(source_ip="2001:db8::1")).items[0]
    assert event.source_ip == "2001:db8::1"
    assert event.timestamp.utcoffset() == timedelta(0)
    assert event.timestamp == BASE_TIME + timedelta(hours=1)
    assert event.ingested_at.tzinfo is UTC or event.ingested_at.utcoffset() == timedelta(0)
    assert event.ingested_at > datetime(2020, 1, 1, tzinfo=UTC)
    assert not hasattr(event, "username")
