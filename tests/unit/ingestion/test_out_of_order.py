"""FR-001-15: definición determinista de "fuera de orden", sin estado entre lotes."""

from pathlib import Path
from typing import Any

from security_anomaly.ingestion import ingest_file, ingest_records
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer


def _event(n: int, timestamp: str) -> dict[str, Any]:
    return {
        "event_id": f"e{n}",
        "timestamp": timestamp,
        "source": "linux-auth",
        "event_type": "authentication",
        "action": "login",
        "outcome": "failure",
    }


def test_fixture_marks_only_events_earlier_than_the_max_seen_before(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(
        fixtures_dir / "out_of_order.json", policy=policy, pseudonymizer=pseudonymizer
    )
    report = result.report
    assert report.out_of_order == (3, 8)
    flagged = {event.position for event in result.events if event.out_of_order}
    assert flagged == {3, 8}
    # el duplicado (5) y el rechazado (6) no se marcan ni actualizan el máximo
    assert [d.position for d in report.duplicates] == [5]
    assert [r.position for r in report.rejections] == [6]
    assert report.total_records == 8


def test_an_equal_timestamp_is_not_out_of_order(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_records(
        [_event(1, "2026-11-12T10:30:00Z"), _event(2, "2026-11-12T10:30:00Z")],
        policy=policy,
        pseudonymizer=pseudonymizer,
    )
    assert result.report.out_of_order == ()
    assert not any(event.out_of_order for event in result.events)


def test_ordered_batches_are_never_marked(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    records = [_event(n, f"2026-11-12T10:30:{n:02d}Z") for n in range(10)]
    result = ingest_records(records, policy=policy, pseudonymizer=pseudonymizer)
    assert result.report.out_of_order == ()


def test_order_is_judged_after_normalizing_to_utc(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_records(
        [_event(1, "2026-11-12T10:30:00Z"), _event(2, "2026-11-12T11:00:00+02:00")],
        policy=policy,
        pseudonymizer=pseudonymizer,
    )
    assert result.report.out_of_order == (2,)  # 11:00+02:00 = 09:00Z, anterior a 10:30Z


def test_no_state_is_kept_between_calls(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    ingest_records([_event(1, "2026-11-12T12:00:00Z")], policy=policy, pseudonymizer=pseudonymizer)
    second = ingest_records(
        [_event(2, "2026-11-12T08:00:00Z")], policy=policy, pseudonymizer=pseudonymizer
    )
    assert second.report.out_of_order == ()
