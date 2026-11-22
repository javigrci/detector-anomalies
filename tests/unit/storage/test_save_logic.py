"""FR-002-02, 06, 07, 09: lógica pura del guardado (sin base de datos)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock

from security_anomaly.schemas.event import Action, Outcome
from security_anomaly.storage.events import (
    INSERT_CHUNK_SIZE,
    chunked,
    content_differs,
    dedupe_events,
    event_to_row,
    save_events,
)
from tests.storage_factory import make_event, make_events

BATCH = uuid.uuid4()


def test_row_has_exactly_the_stored_columns() -> None:
    row = event_to_row(make_event(1), BATCH)
    assert set(row) == {
        "source",
        "event_id",
        "timestamp",
        "event_type",
        "action",
        "outcome",
        "user_pseudonym",
        "source_ip",
        "host",
        "batch_id",
    }
    assert row["batch_id"] == BATCH


def test_row_has_no_username_batch_flags_or_ingestion_time() -> None:
    row = event_to_row(make_event(1), BATCH)
    assert not set(row) & {"username", "out_of_order", "position", "ingested_at"}


def test_row_uses_plain_catalog_values() -> None:
    row = event_to_row(make_event(1, outcome=Outcome.FAILURE, action=Action.SUDO), BATCH)
    assert (row["outcome"], row["action"]) == ("failure", "sudo")
    assert type(row["outcome"]) is str


def test_event_without_user_has_a_null_pseudonym() -> None:
    event = make_event(1).model_copy(update={"user_pseudonym": None})
    assert event_to_row(event, BATCH)["user_pseudonym"] is None


def test_dedupe_keeps_the_first_and_counts_the_repeats() -> None:
    first = make_event(1, event_id="same", host="srv-demo-01")
    second = make_event(2, event_id="same", host="srv-demo-02")
    other = make_event(3, event_id="other")
    unique, repeated = dedupe_events([first, second, other])
    assert [e.event_id for e in unique] == ["other", "same"]
    assert unique[1].host == "srv-demo-01"
    assert repeated == 1


def test_same_event_id_in_different_sources_is_not_a_repeat() -> None:
    a = make_event(1, event_id="x", source="linux-auth")
    b = make_event(2, event_id="x", source="windows-sec")
    assert dedupe_events([a, b])[1] == 0


def test_unique_events_are_sorted_by_key() -> None:
    events = [make_event(i, event_id=name) for i, name in enumerate(["c", "a", "b"])]
    unique, _ = dedupe_events(events)
    assert [e.event_id for e in unique] == ["a", "b", "c"]


def test_chunked_splits_without_losing_items() -> None:
    chunks = list(chunked(list(range(2500)), 1000))
    assert [len(c) for c in chunks] == [1000, 1000, 500]
    assert [x for c in chunks for x in c] == list(range(2500))
    assert list(chunked([], 1000)) == []
    assert INSERT_CHUNK_SIZE == 1000


def _stored_like(event_id: str = "e1") -> dict[str, object]:
    row = event_to_row(make_event(1, event_id=event_id), BATCH)
    return {k: v for k, v in row.items() if k not in {"batch_id"}}


def test_same_content_does_not_differ() -> None:
    row = event_to_row(make_event(1), BATCH)
    assert content_differs(row, _stored_like("evt-000001")) is False


def test_each_content_field_is_compared() -> None:
    incoming = event_to_row(make_event(1), BATCH)
    base = _stored_like("evt-000001")
    changes: dict[str, object] = {
        "timestamp": datetime(2030, 1, 1, tzinfo=UTC),
        "event_type": "other",
        "action": "other",
        "outcome": "unknown",
        "user_pseudonym": "usr_" + "f" * 32,
        "source_ip": "198.51.100.9",
        "host": "otro-host",
    }
    for field, value in changes.items():
        assert content_differs(incoming, {**base, field: value}) is True, field


def test_comparison_ignores_timezone_representation_and_ip_spelling() -> None:
    tz = timezone(timedelta(hours=2))
    event = make_event(
        1, timestamp=datetime(2026, 1, 1, 2, tzinfo=tz), source_ip="2001:0db8:0:0:0:0:0:1"
    )
    incoming = event_to_row(event, BATCH)
    stored = {**_stored_like("evt-000001")}
    stored.update(timestamp=datetime(2026, 1, 1, tzinfo=UTC), source_ip="2001:db8::1")
    stored.update(user_pseudonym=incoming["user_pseudonym"], host=incoming["host"])
    assert content_differs(incoming, stored) is False


def test_null_fields_compare_equal() -> None:
    event = make_event(1).model_copy(
        update={"user_pseudonym": None, "source_ip": None, "host": None}
    )
    incoming = event_to_row(event, BATCH)
    stored = {k: v for k, v in incoming.items() if k != "batch_id"}
    assert content_differs(incoming, stored) is False


def test_empty_input_never_opens_a_connection() -> None:
    engine = MagicMock()
    summary = save_events(engine, [])
    assert (summary.inserted, summary.existing, summary.existing_with_different_content) == (
        0,
        0,
        0,
    )
    engine.begin.assert_not_called()
    engine.connect.assert_not_called()


def test_make_events_helper_is_deterministic() -> None:
    assert make_events(5) == make_events(5)
