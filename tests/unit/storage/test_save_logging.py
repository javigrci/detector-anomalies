"""FR-002-26: el registro del guardado solo lleva recuentos, duración e identificador de lote."""

import logging
import uuid

import pytest

from security_anomaly.schemas.storage import SaveSummary
from security_anomaly.storage.events import log_saved


def test_events_saved_has_only_counts_duration_and_batch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    batch = uuid.uuid4()
    summary = SaveSummary(batch_id=batch, inserted=3, existing=2, existing_with_different_content=1)
    with caplog.at_level(logging.INFO, logger="security_anomaly.storage.events"):
        log_saved(summary, 0.25)
    (record,) = [r for r in caplog.records if r.getMessage() == "events_saved"]
    fields = record.fields  # type: ignore[attr-defined]
    assert fields == {
        "batch_id": str(batch),
        "inserted": 3,
        "existing": 2,
        "existing_with_different_content": 1,
        "duration_ms": 250,
    }
