"""FR-001-19 y FR-001-21: ingesta de lotes válidos, duplicados e informe."""

from pathlib import Path

from security_anomaly.ingestion import ingest_file, ingest_records
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.event import Outcome

EXPECTED_IDS = [f"evt-00000{i}" for i in range(1, 6)]


def test_json_jsonl_and_csv_give_identical_results(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    results = [
        ingest_file(fixtures_dir / name, policy=policy, pseudonymizer=pseudonymizer)
        for name in ("valid.json", "valid.jsonl", "valid.csv")
    ]
    canonical = {result.to_canonical_json() for result in results}
    assert len(canonical) == 1


def test_valid_batch_reports_everything_accepted(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(fixtures_dir / "valid.json", policy=policy, pseudonymizer=pseudonymizer)
    report = result.report
    assert [event.event_id for event in result.events] == EXPECTED_IDS
    assert report.total_records == 5
    assert report.accepted == 5
    assert report.rejected == 0
    assert report.duplicates == ()
    assert report.by_code == {}


def test_ingesting_the_same_file_twice_is_identical(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    first = ingest_file(fixtures_dir / "valid.csv", policy=policy, pseudonymizer=pseudonymizer)
    second = ingest_file(fixtures_dir / "valid.csv", policy=policy, pseudonymizer=pseudonymizer)
    assert first.to_canonical_json() == second.to_canonical_json()


def test_duplicates_keep_the_first_and_report_whether_content_differed(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(
        fixtures_dir / "duplicates.json", policy=policy, pseudonymizer=pseudonymizer
    )
    report = result.report
    assert report.total_records == 4
    assert report.accepted == 2
    assert [(d.position, d.content_differs) for d in report.duplicates] == [
        (3, False),
        (4, True),
    ]
    assert result.events[1].outcome == Outcome.FAILURE  # se conservó la primera aparición
    assert report.total_records == report.accepted + report.rejected + len(report.duplicates)


def test_no_state_is_kept_between_calls(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    record = {
        "event_id": "e1",
        "timestamp": "2026-11-12T10:30:00Z",
        "source": "linux-auth",
        "event_type": "authentication",
        "action": "login",
        "outcome": "failure",
    }
    first = ingest_records([record], policy=policy, pseudonymizer=pseudonymizer)
    second = ingest_records([record], policy=policy, pseudonymizer=pseudonymizer)
    assert first.report.accepted == 1
    assert second.report.accepted == 1
    assert second.report.duplicates == ()


def test_usernames_never_appear_in_the_result(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(fixtures_dir / "valid.json", policy=policy, pseudonymizer=pseudonymizer)
    dumped = result.to_canonical_json()
    for username in ("user001", "user002", "user003"):
        assert username not in dumped
