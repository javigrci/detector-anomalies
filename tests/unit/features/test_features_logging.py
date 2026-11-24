"""FR-003-24: el registro del cálculo lleva solo recuentos, duración y versión del esquema."""

import logging
from datetime import timedelta

import pytest

from security_anomaly.features.pipeline import compute_event_features, compute_features
from security_anomaly.features.schema import FEATURE_SCHEMA_VERSION
from security_anomaly.schemas.event import NormalizedEvent
from tests.feature_factory import BASE, make_event

HISTORY_START = BASE - timedelta(hours=1)
USER = "usr_" + "a" * 32


def _events() -> list[NormalizedEvent]:
    return [
        make_event(
            i,
            event_id=f"SENTINEL-ID-{i}",
            timestamp=BASE + timedelta(seconds=i),
            user=USER,
            ip="192.0.2.77",
            host="SENTINEL-HOST-x",
        )
        for i in range(5)
    ]


def test_features_computed_has_only_counts_duration_and_schema_version(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        vectors = list(compute_features(_events(), history_start=HISTORY_START))
    assert len(vectors) == 5
    (record,) = [r for r in caplog.records if r.getMessage() == "features_computed"]
    fields = record.fields  # type: ignore[attr-defined]
    assert set(fields) == {"events", "incomplete_context", "duration_ms", "schema_version"}
    assert fields["events"] == 5
    assert fields["incomplete_context"] == 0
    assert fields["schema_version"] == FEATURE_SCHEMA_VERSION
    for secret in (USER, "192.0.2.77", "SENTINEL"):
        assert secret not in caplog.text


def test_the_single_event_path_logs_the_same_way(caplog: pytest.LogCaptureFixture) -> None:
    event, *history = _events()
    with caplog.at_level(logging.DEBUG):
        compute_event_features(event, history, history_start=HISTORY_START)
    (record,) = [r for r in caplog.records if r.getMessage() == "features_computed"]
    assert record.fields["events"] == 1  # type: ignore[attr-defined]
    assert "SENTINEL" not in caplog.text and USER not in caplog.text
