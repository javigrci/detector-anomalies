"""FR-001-24: sin clave la ingesta falla cerrado y nunca emite el nombre en claro."""

from pathlib import Path
from typing import Any

import pytest

from security_anomaly.ingestion import ingest_file, ingest_records
from security_anomaly.ingestion.errors import IngestionError, PseudonymKeyMissing
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer


def _event(n: int, **over: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": f"e{n}",
        "timestamp": "2026-11-12T10:30:00Z",
        "source": "linux-auth",
        "event_type": "authentication",
        "action": "login",
        "outcome": "failure",
    }
    event.update(over)
    return event


def test_users_without_a_key_fail_closed(policy: IngestionPolicy) -> None:
    with pytest.raises(PseudonymKeyMissing):
        ingest_records(
            [_event(1, username="user001")], policy=policy, pseudonymizer=Pseudonymizer(None)
        )


def test_a_file_with_users_and_no_key_fails_closed(
    fixtures_dir: Path, policy: IngestionPolicy
) -> None:
    with pytest.raises(PseudonymKeyMissing):
        ingest_file(fixtures_dir / "valid.json", policy=policy, pseudonymizer=Pseudonymizer(None))


def test_no_users_and_no_key_is_fine(policy: IngestionPolicy) -> None:
    result = ingest_records(
        [_event(1), _event(2, username=None), _event(3, username="  ")],
        policy=policy,
        pseudonymizer=Pseudonymizer(None),
    )
    assert result.report.accepted == 3
    assert all(event.user_pseudonym is None for event in result.events)


def test_a_late_user_in_a_mixed_batch_still_fails_closed(policy: IngestionPolicy) -> None:
    records = [_event(n) for n in range(5)] + [_event(5, username="user001")]
    with pytest.raises(PseudonymKeyMissing):
        ingest_records(records, policy=policy, pseudonymizer=Pseudonymizer(None))


def test_the_failure_returns_nothing_and_is_an_ingestion_error(policy: IngestionPolicy) -> None:
    records = [_event(1), _event(2, username="user001")]
    with pytest.raises(IngestionError):
        ingest_records(records, policy=policy, pseudonymizer=Pseudonymizer(None))


def test_users_of_rejected_records_need_no_key(policy: IngestionPolicy) -> None:
    # Un registro rechazado no emite nada, así que no hay nada que seudonimizar.
    result = ingest_records(
        [_event(1, username="user001", source_ip="bad")],
        policy=policy,
        pseudonymizer=Pseudonymizer(None),
    )
    assert result.report.rejected == 1
    assert result.events == ()
