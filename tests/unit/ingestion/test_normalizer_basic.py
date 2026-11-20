"""FR-001-01, FR-001-03 y FR-001-11: camino válido de la normalización."""

from datetime import UTC, datetime, timedelta
from typing import Any

from security_anomaly.ingestion.normalizer import normalize_record
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.event import Action, EventType, Outcome

VALID: dict[str, Any] = {
    "event_id": "evt-000001",
    "timestamp": "2026-11-12T12:30:00+02:00",
    "source": "Linux-Auth",
    "event_type": "authentication",
    "action": "login",
    "outcome": "failure",
    "username": "user001",
    "source_ip": "2001:DB8:0:0:0:0:0:1",
    "host": "SRV-DEMO-01",
}


def _normalize(data: dict[str, Any], policy: IngestionPolicy, pseudonymizer: Pseudonymizer) -> Any:
    return normalize_record(data, position=3, policy=policy, pseudonymizer=pseudonymizer)


def test_valid_event_is_normalized(policy: IngestionPolicy, pseudonymizer: Pseudonymizer) -> None:
    result = _normalize(VALID, policy, pseudonymizer)
    assert result.rejections == ()
    event = result.event
    assert event is not None
    assert event.event_id == "evt-000001"
    assert event.source == "linux-auth"
    assert event.event_type == EventType.AUTHENTICATION
    assert event.action == Action.LOGIN
    assert event.outcome == Outcome.FAILURE
    assert event.host == "srv-demo-01"
    assert event.source_ip == "2001:db8::1"
    assert event.position == 3
    assert event.out_of_order is False


def test_timestamp_is_converted_to_utc(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    event = _normalize(VALID, policy, pseudonymizer).event
    assert event.timestamp == datetime(2026, 11, 12, 10, 30, tzinfo=UTC)
    assert event.timestamp.utcoffset() == timedelta(0)


def test_username_is_replaced_by_a_pseudonym(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    event = _normalize(VALID, policy, pseudonymizer).event
    assert event.user_pseudonym == pseudonymizer.pseudonym("user001")
    assert "user001" not in event.model_dump_json()


def test_absent_and_empty_optionals_become_none(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    data = {k: v for k, v in VALID.items() if k not in {"username", "host"}}
    data["source_ip"] = ""
    event = _normalize(data, policy, pseudonymizer).event
    assert event.user_pseudonym is None
    assert event.source_ip is None
    assert event.host is None


def test_equivalent_inputs_give_identical_events(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    reordered = dict(reversed(list(VALID.items())))
    first = _normalize(VALID, policy, pseudonymizer).event
    second = _normalize(reordered, policy, pseudonymizer).event
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
