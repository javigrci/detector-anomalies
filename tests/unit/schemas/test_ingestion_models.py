"""FR-001-21 y data-model: informe de ingesta, códigos y serialización canónica."""

import json

import pytest
from pydantic import ValidationError

from security_anomaly.schemas.ingestion import (
    BatchRejectionCode,
    Duplicate,
    IngestionReport,
    IngestionResult,
    Rejection,
    RejectionCode,
)

RECORD_CODES = {
    "missing_field",
    "unknown_field",
    "invalid_type",
    "invalid_timestamp",
    "timestamp_out_of_range",
    "invalid_ip",
    "invalid_outcome",
    "invalid_source",
    "field_too_long",
    "invalid_characters",
    "invalid_record",
    "missing_time_context",
}
BATCH_CODES = {
    "file_too_large",
    "too_many_events",
    "invalid_encoding",
    "invalid_format",
    "file_unreadable",
    "not_a_regular_file",
}


def _report(**overrides: object) -> IngestionReport:
    base: dict[str, object] = {
        "total_records": 5,
        "accepted": 2,
        "rejected": 2,
        "rejections": (
            Rejection(position=2, code=RejectionCode.MISSING_FIELD, field="host"),
            Rejection(position=2, code=RejectionCode.MISSING_FIELD, field="source"),
            Rejection(position=4, code=RejectionCode.INVALID_IP, field="source_ip"),
        ),
        "duplicates": (Duplicate(position=5, content_differs=False),),
        "by_code": {"invalid_ip": 1, "missing_field": 2},
    }
    base.update(overrides)
    return IngestionReport.model_validate(base)


def test_record_and_batch_codes_are_exactly_the_documented_ones() -> None:
    assert {code.value for code in RejectionCode} == RECORD_CODES
    assert {code.value for code in BatchRejectionCode} == BATCH_CODES


def test_report_invariant_holds_for_a_consistent_report() -> None:
    report = _report()
    assert report.total_records == report.accepted + report.rejected + len(report.duplicates)
    assert report.catalog_version == 1
    assert report.ignored_lines == 0


def test_report_rejects_an_inconsistent_total() -> None:
    with pytest.raises(ValidationError):
        _report(total_records=9)


def test_rejected_counts_distinct_positions() -> None:
    with pytest.raises(ValidationError):
        _report(rejected=3)  # hay solo 2 posiciones distintas


def test_at_most_five_entries_per_rejected_record() -> None:
    many = tuple(
        Rejection(position=1, code=RejectionCode.MISSING_FIELD, field=f"f{i}") for i in range(6)
    )
    with pytest.raises(ValidationError):
        IngestionReport.model_validate(
            {
                "total_records": 1,
                "accepted": 0,
                "rejected": 1,
                "rejections": many,
                "duplicates": (),
                "by_code": {"missing_field": 6},
            }
        )


def test_canonical_json_is_sorted_compact_and_stable() -> None:
    result = IngestionResult(events=(), report=_report())
    first = result.to_canonical_json()
    assert first == result.to_canonical_json()
    parsed = json.loads(first)
    assert list(parsed) == sorted(parsed)
    assert ", " not in first
    assert ": " not in first


def test_report_exposes_only_codes_fields_positions_and_counts() -> None:
    dumped = json.dumps(_report().model_dump(mode="json"))
    for forbidden in ("value", "input", "username"):
        assert forbidden not in dumped
