"""FR-001-22 y SC-002: ni el informe, ni las excepciones, ni los logs reproducen valores."""

import json
import logging
import traceback
from pathlib import Path

import pytest

from security_anomaly.ingestion import ingest_file
from security_anomaly.ingestion.errors import BatchRejected
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer

SENTINELS = [
    "SENTINEL-UNKNOWN-VALUE",
    "SENTINEL-IP-999",
    "SENTINEL-OUTCOME",
    "SENTINEL-LONG",
    "SENTINEL-CTRL",
    "SENTINEL-NOT-AN-OBJECT",
    "SENTINEL-KEY",
    "rm -rf",
    "SENTINEL-EXTRA-CELL",
    "SENTINEL-NEWLINE",
    "SENTINEL-HEADER",
    "user001",
]
FILES = ["invalid_records.json", "invalid_rows.csv", "unknown_columns.csv"]


def _log_dump(records: list[logging.LogRecord]) -> str:
    return json.dumps(
        [
            {
                "message": record.getMessage(),
                "fields": getattr(record, "fields", None),
                "args": str(record.args),
                "exc": record.exc_text,
            }
            for record in records
        ],
        default=str,
    )


@pytest.mark.parametrize("name", FILES)
def test_no_sentinel_in_report_or_logs(
    name: str,
    fixtures_dir: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        result = ingest_file(fixtures_dir / name, policy=policy, pseudonymizer=pseudonymizer)
    outputs = result.to_canonical_json() + repr(result) + _log_dump(caplog.records)
    for sentinel in SENTINELS:
        assert sentinel not in outputs, sentinel


def test_no_sentinel_in_exceptions(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = tmp_path / "bad.json"
    path.write_text('[{"event_id": "SENTINEL-NOT-AN-OBJECT"', encoding="utf-8")
    with pytest.raises(BatchRejected) as exc:
        ingest_file(path, policy=policy, pseudonymizer=pseudonymizer)
    rendered = "".join(traceback.format_exception(exc.value)) + str(exc.value) + repr(exc.value)
    assert "SENTINEL-NOT-AN-OBJECT" not in rendered


def test_completion_log_has_only_counts_and_duration(
    fixtures_dir: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        ingest_file(
            fixtures_dir / "invalid_records.json", policy=policy, pseudonymizer=pseudonymizer
        )
    completed = [r for r in caplog.records if r.getMessage() == "ingestion_completed"]
    assert len(completed) == 1
    fields = completed[0].fields  # type: ignore[attr-defined]
    assert set(fields) == {
        "total_records",
        "accepted",
        "rejected",
        "duplicates",
        "out_of_order",
        "ignored_lines",
        "by_code",
        "duration_ms",
    }
    assert fields["total_records"] == 16
    assert fields["rejected"] == 16
    assert all(isinstance(value, int) for value in fields["by_code"].values())
