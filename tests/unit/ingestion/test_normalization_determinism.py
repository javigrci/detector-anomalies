"""FR-001-11, 12 y 14, SC-008: salida determinista y categorías acotadas."""

import random
import string
from pathlib import Path
from typing import Any

import pytest

from security_anomaly.ingestion import ingest_file, ingest_records
from security_anomaly.ingestion.normalizer import normalize_record
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.ingestion.readers import read_records
from security_anomaly.schemas.event import Action, EventType
from security_anomaly.schemas.ingestion import RejectionCode as C

BASE: dict[str, Any] = {
    "event_id": "e1",
    "timestamp": "2026-11-12T10:30:00Z",
    "source": "linux-auth",
    "event_type": "authentication",
    "action": "login",
    "outcome": "failure",
}


def _normalize(data: dict[str, Any], policy: IngestionPolicy, pseudonymizer: Pseudonymizer) -> Any:
    return normalize_record(data, position=1, policy=policy, pseudonymizer=pseudonymizer).event


def test_variants_of_the_same_event_normalize_identically(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    records = read_records(fixtures_dir / "variants.json", policy=policy)
    assert len(records) == 6
    dumps = set()
    for record in records:
        assert record.data is not None
        event = _normalize(record.data, policy, pseudonymizer)
        assert event is not None
        dumps.add(event.model_dump_json())
    assert len(dumps) == 1


def test_key_order_does_not_matter(policy: IngestionPolicy, pseudonymizer: Pseudonymizer) -> None:
    data = {**BASE, "username": "user001", "host": "h", "source_ip": "192.0.2.1"}
    reordered = dict(sorted(data.items(), reverse=True))
    assert _normalize(data, policy, pseudonymizer) == _normalize(reordered, policy, pseudonymizer)


def test_equivalent_ipv6_forms_give_the_same_string(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    forms = ["2001:db8::1", "2001:DB8:0:0:0:0:0:1", "2001:0db8:0000:0000:0000:0000:0000:0001"]
    ips = {_normalize({**BASE, "source_ip": f}, policy, pseudonymizer).source_ip for f in forms}
    assert ips == {"2001:db8::1"}


def test_unicode_is_normalized_to_nfc(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    composed = _normalize({**BASE, "host": "café"}, policy, pseudonymizer)
    decomposed = _normalize({**BASE, "host": "café"}, policy, pseudonymizer)
    assert composed.host == decomposed.host


def test_absent_none_and_blank_optionals_are_identical(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    variants: list[dict[str, Any]] = [
        dict(BASE),
        {**BASE, "username": None, "source_ip": None, "host": None},
        {**BASE, "username": "", "source_ip": "", "host": ""},
        {**BASE, "username": "   ", "source_ip": "  ", "host": " \t "},
    ]
    events = [_normalize(v, policy, pseudonymizer) for v in variants]
    assert len({event.model_dump_json() for event in events}) == 1
    assert events[0].user_pseudonym is None
    assert events[0].source_ip is None
    assert events[0].host is None


def test_unknown_event_type_and_action_become_other(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_file(
        fixtures_dir / "unknown_categories.json", policy=policy, pseudonymizer=pseudonymizer
    )
    assert result.report.accepted == 3
    assert [(e.event_type, e.action) for e in result.events] == [
        (EventType.OTHER, Action.OTHER),
        (EventType.OTHER, Action.LOGIN),  # "LOGIN" se normaliza a su forma canónica
        (EventType.AUTHENTICATION, Action.OTHER),
    ]


def test_unknown_outcome_is_rejected_not_grouped(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = normalize_record(
        {**BASE, "outcome": "other"}, position=1, policy=policy, pseudonymizer=pseudonymizer
    )
    assert result.event is None
    assert [(r.code, r.field) for r in result.rejections] == [(C.INVALID_OUTCOME, "outcome")]


@pytest.mark.parametrize("seed", range(5))
def test_category_cardinality_is_bounded_by_the_catalog(
    seed: int, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    rng = random.Random(seed)
    alphabet = string.ascii_letters + string.digits + "-_"
    records = [
        {
            **BASE,
            "event_id": f"e{n}",
            "event_type": "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30))),
            "action": "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30))),
        }
        for n in range(1000)
    ]
    result = ingest_records(records, policy=policy, pseudonymizer=pseudonymizer)
    assert result.report.accepted == 1000
    assert {e.event_type for e in result.events} <= set(EventType)
    assert {e.action for e in result.events} <= set(Action)
    assert len({e.event_type for e in result.events}) <= len(EventType)
    assert len({e.action for e in result.events}) <= len(Action)


def test_the_same_content_in_two_runs_is_byte_identical(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    first = ingest_file(fixtures_dir / "variants.json", policy=policy, pseudonymizer=pseudonymizer)
    second = ingest_file(fixtures_dir / "variants.json", policy=policy, pseudonymizer=pseudonymizer)
    assert first.to_canonical_json() == second.to_canonical_json()
