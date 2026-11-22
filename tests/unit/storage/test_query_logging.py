"""FR-002-26: el registro de la consulta nombra los filtros usados, nunca sus valores."""

import logging

import pytest

from security_anomaly.schemas.storage import EventFilter
from security_anomaly.storage.events import log_queried

PSEUDO = "usr_" + "c" * 32


def test_only_filter_names_counts_and_duration(caplog: pytest.LogCaptureFixture) -> None:
    filters = EventFilter(source="linux-auth", source_ip="192.0.2.77", user_pseudonym=PSEUDO)
    with caplog.at_level(logging.INFO, logger="security_anomaly.storage.events"):
        log_queried(filters, total=42, returned=10, seconds=0.5)
    (record,) = [r for r in caplog.records if r.getMessage() == "events_queried"]
    fields = record.fields  # type: ignore[attr-defined]
    assert fields == {
        "filters": ["source", "source_ip", "user_pseudonym"],
        "total": 42,
        "returned": 10,
        "duration_ms": 500,
    }
    assert "192.0.2.77" not in caplog.text
    assert PSEUDO not in caplog.text
    assert "linux-auth" not in caplog.text
