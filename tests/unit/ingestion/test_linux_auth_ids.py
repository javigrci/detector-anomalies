"""FR-001-09: identificadores deterministas, únicos por posición y con clave."""

import hashlib
import re
from pathlib import Path

import pytest

from security_anomaly.ingestion import ingest_linux_auth
from security_anomaly.ingestion.errors import PseudonymKeyMissing
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.ingestion import IngestionResult


def _run(path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer) -> IngestionResult:
    return ingest_linux_auth(path, policy=policy, pseudonymizer=pseudonymizer, start_year=2026)


def test_reingesting_the_same_file_repeats_the_ids(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = fixtures_dir / "linux_auth_sample.log"
    first = _run(path, policy, pseudonymizer)
    second = _run(path, policy, pseudonymizer)
    assert [e.event_id for e in first.events] == [e.event_id for e in second.events]
    assert first.to_canonical_json() == second.to_canonical_json()


def test_identical_lines_at_different_positions_get_different_ids(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = _run(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer)
    by_position = {e.position: e.event_id for e in result.events}
    assert by_position[12] != by_position[13]  # mismo texto, distinta posición
    assert result.report.duplicates == ()  # no se confunden con duplicados
    assert len(set(by_position.values())) == len(by_position)


def test_ids_have_the_documented_format(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    for event in _run(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer).events:
        assert re.fullmatch(r"la-[0-9a-f]{32}", event.event_id)


def test_another_key_gives_other_ids(
    fixtures_dir: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    other_pseudonymizer: Pseudonymizer,
) -> None:
    path = fixtures_dir / "linux_auth_sample.log"
    ids = {e.event_id for e in _run(path, policy, pseudonymizer).events}
    other = {e.event_id for e in _run(path, policy, other_pseudonymizer).events}
    assert ids.isdisjoint(other)


def test_the_id_is_not_a_plain_hash_of_the_line(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = fixtures_dir / "linux_auth_sample.log"
    first_line = path.read_text(encoding="utf-8").split("\n")[0]
    event_id = _run(path, policy, pseudonymizer).events[0].event_id
    candidates = {
        hashlib.sha256(first_line.encode()).hexdigest()[:32],
        hashlib.sha256(f"1\x00{first_line}".encode()).hexdigest()[:32],
        hashlib.sha256(f"id\x001\x00{first_line}".encode()).hexdigest()[:32],
        hashlib.md5(first_line.encode(), usedforsecurity=False).hexdigest(),
    }
    assert event_id.removeprefix("la-") not in candidates


def test_the_adapter_requires_a_key(fixtures_dir: Path, policy: IngestionPolicy) -> None:
    with pytest.raises(PseudonymKeyMissing):
        _run(fixtures_dir / "linux_auth_sample.log", policy, Pseudonymizer(None))
