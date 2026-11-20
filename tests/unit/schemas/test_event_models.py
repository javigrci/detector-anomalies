"""FR-001-01 y data-model: esquema de entrada, catálogo y evento normalizado."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from security_anomaly.schemas.event import (
    CATALOG_VERSION,
    Action,
    EventType,
    EventV1,
    NormalizedEvent,
    Outcome,
)

SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "specs"
    / "001-ingestion"
    / "contracts"
    / "event-v1.schema.json"
)

VALID: dict[str, Any] = {
    "event_id": "evt-000001",
    "timestamp": "2026-11-12T10:30:00Z",
    "source": "linux-auth",
    "event_type": "authentication",
    "action": "login",
    "outcome": "failure",
    "username": "user001",
    "source_ip": "192.0.2.45",
    "host": "srv-demo-01",
}


def test_valid_event_is_accepted() -> None:
    event = EventV1.model_validate(VALID)
    assert event.event_id == "evt-000001"
    assert event.username == "user001"


@pytest.mark.parametrize(
    "missing", ["event_id", "timestamp", "source", "event_type", "action", "outcome"]
)
def test_required_fields_are_required(missing: str) -> None:
    data = {key: value for key, value in VALID.items() if key != missing}
    with pytest.raises(ValidationError):
        EventV1.model_validate(data)


def test_optional_fields_can_be_omitted() -> None:
    required = {k: v for k, v in VALID.items() if k not in {"username", "source_ip", "host"}}
    event = EventV1.model_validate(required)
    assert event.username is None
    assert event.source_ip is None
    assert event.host is None


def test_unknown_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError) as exc:
        EventV1.model_validate({**VALID, "extra_field": "x"})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_non_string_values_are_not_coerced() -> None:
    with pytest.raises(ValidationError):
        EventV1.model_validate({**VALID, "event_id": 12345})


def test_catalog_v1_matches_the_data_model() -> None:
    assert CATALOG_VERSION == 1
    assert {member.value for member in EventType} == {
        "authentication",
        "privilege_escalation",
        "other",
    }
    assert {member.value for member in Action} == {"login", "invalid_user", "sudo", "other"}
    assert {member.value for member in Outcome} == {"success", "failure", "unknown"}


def test_normalized_event_is_immutable_and_has_no_raw_username() -> None:
    event = NormalizedEvent(
        event_id="e1",
        timestamp=datetime(2026, 11, 12, 10, 30, tzinfo=UTC),
        source="linux-auth",
        event_type=EventType.AUTHENTICATION,
        action=Action.LOGIN,
        outcome=Outcome.SUCCESS,
        user_pseudonym="usr_" + "a" * 32,
        source_ip=None,
        host=None,
        position=1,
    )
    assert not hasattr(event, "username")
    assert event.out_of_order is False
    with pytest.raises(ValidationError):
        event.host = "x"


def test_event_v1_matches_the_json_schema_contract() -> None:
    schema = json.loads(SCHEMA.read_text())
    assert set(EventV1.model_fields) == set(schema["properties"])
    required = {name for name, field in EventV1.model_fields.items() if field.is_required()}
    assert required == set(schema["required"])
    assert schema["additionalProperties"] is False
