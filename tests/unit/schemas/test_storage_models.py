"""FR-002-01, 03, 13, 17: modelos de la persistencia."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from security_anomaly.schemas.event import Action, EventType, Outcome
from security_anomaly.schemas.storage import (
    EventFilter,
    EventPage,
    PurgeResult,
    SaveSummary,
    StoredEvent,
)

PSEUDO = "usr_" + "a" * 32


def test_empty_filter_is_valid() -> None:
    assert EventFilter().source is None


def test_dates_need_timezone() -> None:
    with pytest.raises(ValidationError):
        EventFilter(date_from=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        EventFilter(date_to=datetime(2026, 1, 1))


def test_date_order() -> None:
    a = datetime(2026, 1, 1, tzinfo=UTC)
    EventFilter(date_from=a, date_to=a + timedelta(seconds=1))
    with pytest.raises(ValidationError):
        EventFilter(date_from=a, date_to=a)
    with pytest.raises(ValidationError):
        EventFilter(date_from=a, date_to=a - timedelta(days=1))


def test_dates_are_normalized_to_utc() -> None:
    tz = timezone(timedelta(hours=2))
    f = EventFilter(date_from=datetime(2026, 1, 1, 2, tzinfo=tz))
    assert f.date_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert f.date_from is not None and f.date_from.utcoffset() == timedelta(0)


@pytest.mark.parametrize("source", ["Linux", "-x", "a b", "", "a" * 65, "x;y"])
def test_source_format(source: str) -> None:
    with pytest.raises(ValidationError):
        EventFilter(source=source)


def test_valid_source() -> None:
    assert EventFilter(source="linux-auth").source == "linux-auth"


def test_catalog_values_only() -> None:
    f = EventFilter.model_validate(
        {"event_type": "authentication", "action": "sudo", "outcome": "failure"}
    )
    assert (f.event_type, f.action, f.outcome) == (
        EventType.AUTHENTICATION,
        Action.SUDO,
        Outcome.FAILURE,
    )
    for kwargs in ({"event_type": "x"}, {"action": "x"}, {"outcome": "x"}):
        with pytest.raises(ValidationError):
            EventFilter.model_validate(kwargs)


def test_ip_is_normalized_and_validated() -> None:
    assert (
        EventFilter(source_ip="2001:0db8:0000:0000:0000:0000:0000:0001").source_ip == "2001:db8::1"
    )
    assert EventFilter(source_ip="2001:db8::1").source_ip == "2001:db8::1"
    assert EventFilter(source_ip="192.0.2.1").source_ip == "192.0.2.1"
    for bad in ("999.1.1.1", "abc", "1.1.1", "192.0.2.1; DROP TABLE events", ""):
        with pytest.raises(ValidationError):
            EventFilter(source_ip=bad)


def test_pseudonym_only_never_a_real_name() -> None:
    assert EventFilter(user_pseudonym=PSEUDO).user_pseudonym == PSEUDO
    for bad in ("user001", "usr_abc", "usr_" + "A" * 32, "usr_" + "a" * 33, "root"):
        with pytest.raises(ValidationError):
            EventFilter(user_pseudonym=bad)


def test_filter_error_does_not_echo_value() -> None:
    with pytest.raises(ValidationError) as exc:
        EventFilter(user_pseudonym="SENTINEL-USER-x")
    assert "SENTINEL-USER-x" not in str(exc.value)


def test_models_are_frozen() -> None:
    f = EventFilter()
    with pytest.raises(ValidationError):
        f.source = "x"


def _stored(**kw: object) -> StoredEvent:
    base: dict[str, object] = {
        "source": "linux-auth",
        "event_id": "e1",
        "timestamp": datetime(2026, 1, 1, 3, tzinfo=timezone(timedelta(hours=2))),
        "event_type": EventType.AUTHENTICATION,
        "action": Action.LOGIN,
        "outcome": Outcome.SUCCESS,
        "user_pseudonym": PSEUDO,
        "source_ip": "192.0.2.1",
        "host": "srv-demo-01",
        "ingested_at": datetime(2026, 1, 2, tzinfo=UTC),
        "batch_id": uuid.uuid4(),
    }
    base.update(kw)
    return StoredEvent.model_validate(base)


def test_stored_event_is_utc() -> None:
    e = _stored()
    assert e.timestamp == datetime(2026, 1, 1, 1, tzinfo=UTC)
    assert e.timestamp.utcoffset() == timedelta(0)
    assert e.ingested_at.utcoffset() == timedelta(0)


def test_stored_event_has_no_username_or_batch_flags() -> None:
    fields = set(StoredEvent.model_fields)
    assert not fields & {"username", "out_of_order", "position"}
    assert {"ingested_at", "batch_id", "user_pseudonym"} <= fields


def test_stored_event_is_frozen() -> None:
    with pytest.raises(ValidationError):
        _stored().host = "x"


def test_event_page() -> None:
    page = EventPage(items=(_stored(),), total=1, limit=100, offset=0)
    assert page.total == 1 and len(page.items) == 1
    with pytest.raises(ValidationError):
        EventPage(items=(), total=-1, limit=100, offset=0)


def test_save_summary_invariant_and_counts() -> None:
    s = SaveSummary(
        batch_id=uuid.uuid4(), inserted=3, existing=2, existing_with_different_content=1
    )
    assert s.inserted + s.existing == 5
    with pytest.raises(ValidationError):
        SaveSummary(
            batch_id=uuid.uuid4(), inserted=1, existing=1, existing_with_different_content=2
        )
    with pytest.raises(ValidationError):
        SaveSummary(
            batch_id=uuid.uuid4(), inserted=-1, existing=0, existing_with_different_content=0
        )


def test_purge_result() -> None:
    r = PurgeResult(
        retention_days=90, cutoff=datetime(2026, 1, 1, tzinfo=UTC), dry_run=True, affected=0
    )
    assert r.dry_run and r.affected == 0
