"""FR-002-26: el registro de la purga lleva solo recuentos, cutoff y duración."""

import logging
from datetime import UTC, datetime

import pytest

from security_anomaly.schemas.storage import PurgeResult
from security_anomaly.storage.retention import log_purged


def test_events_purged_has_only_counts_cutoff_and_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cutoff = datetime(2026, 3, 1, tzinfo=UTC)
    result = PurgeResult(retention_days=90, cutoff=cutoff, dry_run=False, affected=12)
    with caplog.at_level(logging.INFO, logger="security_anomaly.storage.retention"):
        log_purged(result, 1.5)
    (record,) = [r for r in caplog.records if r.getMessage() == "events_purged"]
    assert record.fields == {  # type: ignore[attr-defined]
        "retention_days": 90,
        "cutoff": cutoff.isoformat(),
        "dry_run": False,
        "affected": 12,
        "duration_ms": 1500,
    }
