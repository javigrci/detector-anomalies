"""FR-002-16, 24: validación y forma de la consulta de rango (sin base de datos)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from security_anomaly.storage.events import build_range_statement, read_range

START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=1)


def _compile(statement: object) -> tuple[str, dict[str, object]]:
    compiled = statement.compile(dialect=postgresql.dialect())  # type: ignore[attr-defined,no-untyped-call]
    return str(compiled), dict(compiled.params)


@pytest.mark.parametrize(
    ("start", "end", "chunk"),
    [
        (datetime(2026, 1, 1), END, 100),
        (START, datetime(2026, 1, 2), 100),
        (END, START, 100),
        (START, START, 100),
        (START, END, 0),
        (START, END, -5),
    ],
)
def test_invalid_arguments_are_rejected_at_call_time_without_touching_the_database(
    start: datetime, end: datetime, chunk: int
) -> None:
    engine = MagicMock()
    with pytest.raises(ValueError, match=r"\S"):
        read_range(engine, start, end, chunk_size=chunk)  # sin iterar
    engine.connect.assert_not_called()
    engine.begin.assert_not_called()


def test_statement_is_half_open_and_ordered() -> None:
    text, params = _compile(build_range_statement(START, END, 500, None))
    assert "events.timestamp >= " in text
    assert "events.timestamp < " in text
    assert "events.timestamp <= " not in text
    assert "ORDER BY events.timestamp, events.source, events.event_id" in text
    assert "LIMIT" in text and 500 in params.values()
    assert START in params.values() and END in params.values()


def test_keyset_condition_uses_a_tuple_comparison_with_bound_values() -> None:
    after = (START + timedelta(hours=1), "linux-auth", "evt-000042")
    text, params = _compile(build_range_statement(START, END, 500, after))
    assert "(events.timestamp, events.source, events.event_id) > (" in text
    assert "evt-000042" not in text
    assert "evt-000042" in params.values()
    assert "OFFSET" not in text


def test_first_chunk_has_no_keyset_condition() -> None:
    text, _ = _compile(build_range_statement(START, END, 500, None))
    assert "(events.timestamp, events.source, events.event_id) >" not in text
