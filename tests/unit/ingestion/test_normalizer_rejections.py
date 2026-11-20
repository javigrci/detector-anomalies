"""FR-001-04, 05, 13 y 16: cada código de rechazo, con su campo y sin valores."""

from pathlib import Path
from typing import Any

import pytest

from security_anomaly.ingestion import ingest_file
from security_anomaly.ingestion.normalizer import normalize_record
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.ingestion.readers import read_records
from security_anomaly.schemas.ingestion import RejectionCode as C

EXPECTED: dict[int, list[tuple[C, str | None]]] = {
    1: [(C.MISSING_FIELD, "source"), (C.MISSING_FIELD, "action")],
    2: [(C.UNKNOWN_FIELD, "extra_field")],
    3: [(C.INVALID_TYPE, "event_id")],
    4: [(C.INVALID_TIMESTAMP, "timestamp")],
    5: [(C.TIMESTAMP_OUT_OF_RANGE, "timestamp")],
    6: [(C.TIMESTAMP_OUT_OF_RANGE, "timestamp")],
    7: [(C.INVALID_IP, "source_ip")],
    8: [(C.INVALID_IP, "source_ip")],
    9: [(C.INVALID_OUTCOME, "outcome")],
    10: [(C.INVALID_SOURCE, "source")],
    11: [(C.FIELD_TOO_LONG, "host")],
    12: [(C.INVALID_CHARACTERS, "username")],
    13: [(C.INVALID_RECORD, None)],
    14: [(C.UNKNOWN_FIELD, "<invalid-name>")],
    15: [(C.UNKNOWN_FIELD, f"unk{i}") for i in range(1, 6)],
    16: [(C.MISSING_FIELD, "event_id")],
}

BASE: dict[str, Any] = {
    "event_id": "e1",
    "timestamp": "2026-11-12T10:30:00Z",
    "source": "linux-auth",
    "event_type": "authentication",
    "action": "login",
    "outcome": "failure",
}


@pytest.mark.parametrize("position", sorted(EXPECTED))
def test_each_invalid_record_gets_its_code_and_field(
    position: int, fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    records = read_records(fixtures_dir / "invalid_records.json", policy=policy)
    record = records[position - 1]
    result = normalize_record(
        record.data, position=record.position, policy=policy, pseudonymizer=pseudonymizer
    )
    assert result.event is None
    assert [(r.code, r.field) for r in result.rejections] == EXPECTED[position]
    assert {r.position for r in result.rejections} == {position}


def test_several_semantic_errors_are_reported_together(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = normalize_record(
        {**BASE, "source_ip": "nope", "outcome": "maybe"},
        position=1,
        policy=policy,
        pseudonymizer=pseudonymizer,
    )
    assert [(r.code, r.field) for r in result.rejections] == [
        (C.INVALID_OUTCOME, "outcome"),
        (C.INVALID_IP, "source_ip"),
    ]


def test_non_object_record_is_invalid_record(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = normalize_record(None, position=7, policy=policy, pseudonymizer=pseudonymizer)
    assert result.event is None
    assert [(r.code, r.field) for r in result.rejections] == [(C.INVALID_RECORD, None)]


def test_safe_unknown_field_name_is_reported_and_hostile_one_is_masked(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    for name, expected in [
        ("legacy.field-1", "legacy.field-1"),
        ("with space", "<invalid-name>"),
        ("x" * 65, "<invalid-name>"),
        ("ctrl\x07char", "<invalid-name>"),
        ("ñandú", "<invalid-name>"),
    ]:
        result = normalize_record(
            {**BASE, name: "v"}, position=1, policy=policy, pseudonymizer=pseudonymizer
        )
        assert [(r.code, r.field) for r in result.rejections] == [(C.UNKNOWN_FIELD, expected)]


def test_a_fully_invalid_batch_produces_a_report_not_an_error(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(
        fixtures_dir / "invalid_records.json", policy=policy, pseudonymizer=pseudonymizer
    )
    report = result.report
    assert result.events == ()
    assert report.total_records == 16
    assert report.accepted == 0
    assert report.rejected == 16
    assert report.by_code[C.MISSING_FIELD.value] == 3  # posiciones 1 (x2) y 16
    assert report.by_code[C.UNKNOWN_FIELD.value] == 7  # 1 + 1 + 5


def test_csv_rows_with_wrong_shape_or_control_characters_are_rejected(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(
        fixtures_dir / "invalid_rows.csv", policy=policy, pseudonymizer=pseudonymizer
    )
    report = result.report
    assert [event.event_id for event in result.events] == ["row-001", "row-005"]
    assert [(r.position, r.code, r.field) for r in report.rejections] == [
        (2, C.INVALID_RECORD, None),
        (3, C.INVALID_RECORD, None),
        (4, C.INVALID_CHARACTERS, "host"),
    ]
    assert report.total_records == 5


def test_unknown_csv_columns_are_rejected_with_safe_names(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(
        fixtures_dir / "unknown_columns.csv", policy=policy, pseudonymizer=pseudonymizer
    )
    assert result.events == ()
    assert [(r.code, r.field) for r in result.report.rejections] == [
        (C.UNKNOWN_FIELD, "note"),
        (C.UNKNOWN_FIELD, "<invalid-name>"),
    ]
