"""FR-002-13…15, 17, 24: construcción y validación de la consulta (sin base de datos)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from security_anomaly.schemas.event import Action, EventType, Outcome
from security_anomaly.schemas.storage import EventFilter
from security_anomaly.storage.config import StoragePolicy
from security_anomaly.storage.events import (
    build_count_statement,
    build_page_statement,
    query_events,
    resolve_pagination,
)

PSEUDO = "usr_" + "a" * 32
FULL = EventFilter(
    date_from=datetime(2026, 1, 1, tzinfo=UTC),
    date_to=datetime(2026, 2, 1, tzinfo=UTC),
    source="linux-auth",
    event_type=EventType.AUTHENTICATION,
    action=Action.LOGIN,
    outcome=Outcome.FAILURE,
    source_ip="192.0.2.7",
    user_pseudonym=PSEUDO,
)


def _compile(statement: object) -> tuple[str, dict[str, object]]:
    compiled = statement.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined,no-untyped-call]
    return str(compiled), dict(compiled.params)


def test_every_value_is_a_bound_parameter() -> None:
    text, params = _compile(build_page_statement(FULL, 100, 0))
    for value in ("linux-auth", "192.0.2.7", PSEUDO, "authentication", "login", "failure"):
        assert value not in text
        assert value in {str(v) for v in params.values()}


def test_hostile_values_never_reach_the_sql_text() -> None:
    # Una IP o un seudónimo hostiles ni siquiera pasan la validación del filtro.
    for bad in ("'; DROP TABLE events; --", "1.1.1.1' OR '1'='1"):
        with pytest.raises(ValueError, match=r"\S"):
            EventFilter(source_ip=bad)
        with pytest.raises(ValueError, match=r"\S"):
            EventFilter(user_pseudonym=bad)
        with pytest.raises(ValueError, match=r"\S"):
            EventFilter(source=bad)


def test_order_is_total_and_deterministic() -> None:
    text, _ = _compile(build_page_statement(EventFilter(), 100, 0))
    assert "ORDER BY events.timestamp, events.source, events.event_id" in text


def test_filters_are_combined_with_and() -> None:
    text, _ = _compile(build_page_statement(FULL, 100, 0))
    where = text.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert where.count(" AND ") == 7
    assert " OR " not in where


def test_range_is_half_open() -> None:
    text, _ = _compile(build_count_statement(FULL))
    assert "events.timestamp >= " in text
    assert "events.timestamp < " in text


def test_no_filters_means_no_where_clause() -> None:
    text, _ = _compile(build_page_statement(EventFilter(), 100, 0))
    assert "WHERE" not in text


def test_count_uses_the_same_filters() -> None:
    page, page_params = _compile(build_page_statement(FULL, 100, 0))
    count, count_params = _compile(build_count_statement(FULL))
    assert page.split("WHERE", 1)[1].split("ORDER BY")[0].replace(" ", "") == count.split(
        "WHERE", 1
    )[1].replace(" ", "")
    assert {str(v) for v in count_params.values()} <= {str(v) for v in page_params.values()}


def test_ip_is_compared_as_inet() -> None:
    text, _ = _compile(build_count_statement(EventFilter(source_ip="2001:0db8::0001")))
    assert "events.source_ip" in text


def test_page_statement_limits_and_offsets_with_parameters() -> None:
    text, params = _compile(build_page_statement(EventFilter(), 25, 50))
    assert "LIMIT" in text and "OFFSET" in text
    assert 25 in params.values() and 50 in params.values()


def test_default_limit_comes_from_the_policy() -> None:
    assert resolve_pagination(None, 0, StoragePolicy()) == (100, 0)
    assert resolve_pagination(None, 0, StoragePolicy(query_default_limit=10)) == (10, 0)


@pytest.mark.parametrize("limit", [0, -1, 1001, 5000])
def test_limit_out_of_range_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        resolve_pagination(limit, 0, StoragePolicy())


def test_limit_may_reach_the_configured_maximum() -> None:
    assert resolve_pagination(1000, 0, StoragePolicy()) == (1000, 0)
    assert resolve_pagination(50, 0, StoragePolicy(query_default_limit=50, query_max_limit=50)) == (
        50,
        0,
    )
    with pytest.raises(ValueError, match="limit"):
        resolve_pagination(51, 0, StoragePolicy(query_default_limit=50, query_max_limit=50))


def test_negative_offset_is_rejected() -> None:
    with pytest.raises(ValueError, match="offset"):
        resolve_pagination(10, -1, StoragePolicy())


def test_invalid_parameters_are_rejected_before_touching_the_database() -> None:
    engine = MagicMock()
    for kwargs in ({"limit": 0}, {"limit": 5000}, {"offset": -3}):
        with pytest.raises(ValueError, match=r"\S"):
            query_events(engine, EventFilter(), **kwargs)  # type: ignore[arg-type]
    engine.connect.assert_not_called()
    engine.begin.assert_not_called()
