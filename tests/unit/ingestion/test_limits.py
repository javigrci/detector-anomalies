"""FR-001-02, 17 y 18: límites de archivo y de lote, errores de lectura y entradas vacías."""

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from security_anomaly.ingestion import ingest_file, ingest_records
from security_anomaly.ingestion.errors import BatchRejected
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.ingestion import BatchRejectionCode as B
from security_anomaly.schemas.ingestion import RejectionCode as C


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


def _write(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def test_oversized_file_is_rejected_fast_without_reading_it(
    tmp_path: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "huge.json"
    with path.open("wb") as handle:
        handle.truncate(policy.max_file_bytes + 1)  # archivo disperso, no ocupa disco

    def _must_not_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no se debe abrir un archivo que excede el límite")

    monkeypatch.setattr(Path, "open", _must_not_open)
    monkeypatch.setattr(Path, "read_bytes", _must_not_open)
    monkeypatch.setattr(Path, "read_text", _must_not_open)
    started = time.perf_counter()
    with pytest.raises(BatchRejected) as exc:
        ingest_file(path, policy=policy, pseudonymizer=pseudonymizer)
    assert time.perf_counter() - started < 1
    assert exc.value.code == B.FILE_TOO_LARGE
    assert exc.value.limit == policy.max_file_bytes


@pytest.mark.parametrize("name", ["too_many.json", "too_many.jsonl"])
def test_too_many_events_rejects_the_whole_batch(
    name: str, tmp_path: Path, pseudonymizer: Pseudonymizer
) -> None:
    policy = IngestionPolicy(max_events_per_batch=3)
    events = [_event(n) for n in range(4)]
    path = tmp_path / name
    if name.endswith("l"):
        path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    else:
        _write(path, events)
    with pytest.raises(BatchRejected) as exc:
        ingest_file(path, policy=policy, pseudonymizer=pseudonymizer)
    assert exc.value.code == B.TOO_MANY_EVENTS
    assert exc.value.limit == 3


def test_default_limit_is_10000_events(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    ok = _write(tmp_path / "ok.json", [_event(n) for n in range(10_000)])
    assert ingest_file(ok, policy=policy, pseudonymizer=pseudonymizer).report.accepted == 10_000
    over = _write(tmp_path / "over.json", [_event(n) for n in range(10_001)])
    with pytest.raises(BatchRejected) as exc:
        ingest_file(over, policy=policy, pseudonymizer=pseudonymizer)
    assert exc.value.code == B.TOO_MANY_EVENTS


def test_a_long_field_rejects_only_that_record(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_records(
        [_event(1), _event(2, host="h" * 257), _event(3, host="h" * 256)],
        policy=policy,
        pseudonymizer=pseudonymizer,
    )
    assert [event.event_id for event in result.events] == ["e1", "e3"]
    assert [(r.position, r.code, r.field) for r in result.report.rejections] == [
        (2, C.FIELD_TOO_LONG, "host")
    ]


def test_custom_field_limit_applies(pseudonymizer: Pseudonymizer) -> None:
    # El límite aplica a todos los campos: 20 deja pasar el timestamp (20 caracteres) y el resto.
    policy = IngestionPolicy(max_field_length=20)
    result = ingest_records(
        [_event(1, event_id="x" * 21), _event(2, event_id="x" * 20)],
        policy=policy,
        pseudonymizer=pseudonymizer,
    )
    assert [event.event_id for event in result.events] == ["x" * 20]
    assert [(r.code, r.field) for r in result.report.rejections] == [(C.FIELD_TOO_LONG, "event_id")]


def test_missing_file_is_unreadable(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    with pytest.raises(BatchRejected) as exc:
        ingest_file(tmp_path / "nope.json", policy=policy, pseudonymizer=pseudonymizer)
    assert exc.value.code == B.FILE_UNREADABLE


def test_directory_is_not_a_regular_file(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    folder = tmp_path / "dir.json"
    folder.mkdir()
    with pytest.raises(BatchRejected) as exc:
        ingest_file(folder, policy=policy, pseudonymizer=pseudonymizer)
    assert exc.value.code == B.NOT_A_REGULAR_FILE


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora los permisos de lectura")
def test_unreadable_file_is_rejected(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = _write(tmp_path / "secret.json", [_event(1)])
    path.chmod(0)
    try:
        with pytest.raises(BatchRejected) as exc:
            ingest_file(path, policy=policy, pseudonymizer=pseudonymizer)
    finally:
        path.chmod(0o600)
    assert exc.value.code == B.FILE_UNREADABLE


def test_invalid_utf8_is_rejected(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = tmp_path / "latin1.json"
    path.write_bytes(b'[{"event_id": "caf\xe9"}]')
    with pytest.raises(BatchRejected) as exc:
        ingest_file(path, policy=policy, pseudonymizer=pseudonymizer)
    assert exc.value.code == B.INVALID_ENCODING


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("empty.json", b""),
        ("blank.json", b"  \n\t "),
        ("list.json", b"[]"),
        ("empty.jsonl", b""),
        ("empty.csv", b""),
        ("header_only.csv", b"event_id,timestamp\n"),
    ],
)
def test_empty_inputs_are_valid_and_give_zero_records(
    name: str,
    content: bytes,
    tmp_path: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
) -> None:
    path = tmp_path / name
    path.write_bytes(content)
    report = ingest_file(path, policy=policy, pseudonymizer=pseudonymizer).report
    assert report.total_records == 0
    assert report.accepted == 0
    assert report.rejected == 0


def test_single_object_json_is_an_invalid_format(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    with pytest.raises(BatchRejected) as exc:
        ingest_file(fixtures_dir / "single_object.json", policy=policy, pseudonymizer=pseudonymizer)
    assert exc.value.code == B.INVALID_FORMAT


def test_jsonl_with_an_invalid_first_line_is_an_invalid_format(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = tmp_path / "bad_first.jsonl"
    path.write_text('{"event_id": \n{"event_id": "x"}\n', encoding="utf-8")
    with pytest.raises(BatchRejected) as exc:
        ingest_file(path, policy=policy, pseudonymizer=pseudonymizer)
    assert exc.value.code == B.INVALID_FORMAT


def test_jsonl_with_a_later_invalid_line_only_rejects_that_record(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = tmp_path / "bad_later.jsonl"
    path.write_text(json.dumps(_event(1)) + "\nthis is not json\n" + json.dumps(_event(3)) + "\n")
    result = ingest_file(path, policy=policy, pseudonymizer=pseudonymizer)
    assert [event.event_id for event in result.events] == ["e1", "e3"]
    assert [(r.position, r.code) for r in result.report.rejections] == [(2, C.INVALID_RECORD)]
