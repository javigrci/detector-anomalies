"""FR-001-17: límites configurables con los valores iniciales de SPEC §4.3."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from security_anomaly.core.config import ConfigError
from security_anomaly.ingestion.policy import IngestionPolicy


def test_defaults_match_the_spec() -> None:
    policy = IngestionPolicy()
    assert policy.max_file_bytes == 10 * 1024 * 1024
    assert policy.max_events_per_batch == 10_000
    assert policy.max_events_per_dataset == 100_000
    assert policy.max_field_length == 256
    assert policy.timestamp_min == datetime(2000, 1, 1, tzinfo=UTC)
    assert policy.timestamp_max == datetime(2100, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "field",
    ["max_file_bytes", "max_events_per_batch", "max_events_per_dataset", "max_field_length"],
)
def test_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        IngestionPolicy.model_validate({field: 0})


def test_timestamp_range_must_be_ordered_and_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        IngestionPolicy(
            timestamp_min=datetime(2050, 1, 1, tzinfo=UTC),
            timestamp_max=datetime(2040, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(ValidationError):
        IngestionPolicy(timestamp_min=datetime(2000, 1, 1))  # sin zona horaria


def test_from_environ_reads_overrides() -> None:
    policy = IngestionPolicy.from_environ(
        {
            "INGEST_MAX_EVENTS_PER_BATCH": "5",
            "INGEST_MAX_FIELD_LENGTH": "64",
            "INGEST_TIMESTAMP_MIN": "2020-01-01T00:00:00+00:00",
        }
    )
    assert policy.max_events_per_batch == 5
    assert policy.max_field_length == 64
    assert policy.timestamp_min == datetime(2020, 1, 1, tzinfo=UTC)
    assert policy.max_file_bytes == 10 * 1024 * 1024


def test_from_environ_blank_means_default() -> None:
    policy = IngestionPolicy.from_environ({"INGEST_MAX_FILE_BYTES": "  "})
    assert policy.max_file_bytes == 10 * 1024 * 1024


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("INGEST_MAX_FILE_BYTES", "-1"),
        ("INGEST_MAX_EVENTS_PER_BATCH", "many-secret"),
        ("INGEST_TIMESTAMP_MAX", "yesterday-secret"),
        ("INGEST_TIMESTAMP_MIN", "2020-01-01T00:00:00"),  # sin zona horaria
        ("INGEST_TIMESTAMP_MAX", "1999-01-01T00:00:00+00:00"),  # anterior al mínimo
    ],
)
def test_from_environ_errors_name_the_variable_not_the_value(variable: str, value: str) -> None:
    with pytest.raises(ConfigError) as exc:
        IngestionPolicy.from_environ({variable: value})
    message = str(exc.value)
    assert variable in message
    if len(value) > 12:
        assert value not in message
