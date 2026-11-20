"""FR-001-02: lectura de JSON, JSON Lines y CSV con posiciones 1-based."""

from pathlib import Path

import pytest

from security_anomaly.ingestion.errors import BatchRejected
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.readers import read_records
from security_anomaly.schemas.ingestion import BatchRejectionCode

EXPECTED_IDS = [f"evt-00000{i}" for i in range(1, 6)]


def _ids(path: Path, policy: IngestionPolicy) -> list[object]:
    records = read_records(path, policy=policy)
    return [record.data["event_id"] if record.data else None for record in records]


@pytest.mark.parametrize("name", ["valid.json", "valid.jsonl", "valid.csv"])
def test_every_format_yields_the_same_events(
    name: str, fixtures_dir: Path, policy: IngestionPolicy
) -> None:
    records = read_records(fixtures_dir / name, policy=policy)
    assert [record.position for record in records] == [1, 2, 3, 4, 5]
    assert _ids(fixtures_dir / name, policy) == EXPECTED_IDS


def test_json_and_csv_expose_the_same_field_values(
    fixtures_dir: Path, policy: IngestionPolicy
) -> None:
    from_json = read_records(fixtures_dir / "valid.json", policy=policy)[2].data
    from_csv = read_records(fixtures_dir / "valid.csv", policy=policy)[2].data
    assert from_json is not None
    assert from_csv is not None
    for key in ("event_id", "timestamp", "source", "outcome", "username", "source_ip", "host"):
        assert from_json[key] == from_csv[key]


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("a.json", "[]"),
        ("a.JSON", "[]"),
        ("a.jsonl", ""),
        ("a.ndjson", ""),
        ("a.csv", "event_id\n"),
    ],
)
def test_format_is_detected_by_extension(
    name: str, content: str, tmp_path: Path, policy: IngestionPolicy
) -> None:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    assert read_records(path, policy=policy) == []


def test_unknown_extension_is_rejected(tmp_path: Path, policy: IngestionPolicy) -> None:
    path = tmp_path / "events.xml"
    path.write_text("<a/>", encoding="utf-8")
    with pytest.raises(BatchRejected) as exc:
        read_records(path, policy=policy)
    assert exc.value.code == BatchRejectionCode.INVALID_FORMAT


def test_explicit_format_overrides_the_extension(tmp_path: Path, policy: IngestionPolicy) -> None:
    path = tmp_path / "events.txt"
    path.write_text('[{"event_id": "x"}]', encoding="utf-8")
    records = read_records(path, policy=policy, fmt="json")
    assert records[0].data == {"event_id": "x"}


def test_utf8_bom_is_tolerated(tmp_path: Path, policy: IngestionPolicy) -> None:
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'[{"event_id": "x"}]')
    assert read_records(path, policy=policy)[0].data == {"event_id": "x"}


def test_csv_header_maps_columns_by_name(tmp_path: Path, policy: IngestionPolicy) -> None:
    path = tmp_path / "cols.csv"
    path.write_text("outcome,event_id\nfailure,e1\n", encoding="utf-8")
    data = read_records(path, policy=policy)[0].data
    assert data == {"outcome": "failure", "event_id": "e1"}
