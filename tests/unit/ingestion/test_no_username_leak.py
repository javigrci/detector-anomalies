"""FR-001-25 y SC-006: el nombre de usuario original no sale en ninguna salida."""

import json
import logging
import traceback
from pathlib import Path
from typing import Any

import pytest

from security_anomaly.ingestion import ingest_file, ingest_records
from security_anomaly.ingestion.errors import PseudonymKeyMissing
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer

USERS = ["user001", "user002", "user003", "SENTINEL-USER-REJECTED", "SENTINEL-USER-UNKNOWN-FIELD"]
FILES = [
    "valid.json",
    "valid.jsonl",
    "valid.csv",
    "duplicates.json",
    "invalid_records.json",
    "invalid_rows.csv",
    "variants.json",
    "out_of_order.json",
]


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


def _log_dump(records: list[logging.LogRecord]) -> str:
    return json.dumps(
        [
            {
                "message": r.getMessage(),
                "fields": getattr(r, "fields", None),
                "args": str(r.args),
                "exc": r.exc_text,
                "name": r.name,
            }
            for r in records
        ],
        default=str,
    )


@pytest.mark.parametrize("name", FILES)
def test_fixture_outputs_never_contain_a_username(
    name: str,
    fixtures_dir: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        result = ingest_file(fixtures_dir / name, policy=policy, pseudonymizer=pseudonymizer)
    outputs = (
        result.to_canonical_json()
        + repr(result)
        + str(result.report)
        + "".join(repr(event) for event in result.events)
        + _log_dump(caplog.records)
    )
    for user in USERS:
        assert user not in outputs, user


def test_users_of_rejected_records_do_not_leak(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer, caplog: pytest.LogCaptureFixture
) -> None:
    records = [
        _event(1, username="SENTINEL-USER-REJECTED", source_ip="not-an-ip"),
        _event(2, username="SENTINEL-USER-UNKNOWN-FIELD", surprise="x"),
        _event(3, username="SENTINEL-USER-REJECTED", timestamp="yesterday"),
        _event(4, username="SENTINEL-USER-REJECTED", outcome="maybe"),
    ]
    with caplog.at_level(logging.DEBUG):
        result = ingest_records(records, policy=policy, pseudonymizer=pseudonymizer)
    assert result.report.rejected == 4
    outputs = result.to_canonical_json() + repr(result) + _log_dump(caplog.records)
    assert "SENTINEL-USER" not in outputs


def test_the_missing_key_failure_does_not_expose_the_user(policy: IngestionPolicy) -> None:
    with pytest.raises(PseudonymKeyMissing) as exc:
        ingest_records(
            [_event(1, username="SENTINEL-USER-REJECTED")],
            policy=policy,
            pseudonymizer=Pseudonymizer(None),
        )
    rendered = "".join(traceback.format_exception(exc.value)) + str(exc.value) + repr(exc.value)
    assert "SENTINEL-USER" not in rendered
