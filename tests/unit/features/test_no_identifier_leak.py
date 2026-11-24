"""FR-003-23, SC-006: ningún identificador sale en los vectores, el esquema o los errores."""

import json
from datetime import timedelta

import pytest

from security_anomaly.features.errors import FeatureError
from security_anomaly.features.pipeline import compute_event_features, compute_features
from security_anomaly.features.schema import FEATURE_SCHEMA
from security_anomaly.schemas.event import NormalizedEvent
from tests.feature_factory import BASE, make_event

HISTORY_START = BASE - timedelta(hours=1)
USER = "usr_" + "d" * 32
IP = "192.0.2.77"
IPV6 = "2001:db8::77"
HOST = "SENTINEL-HOST-leak"
EVENT_ID = "SENTINEL-ID-leak"


def _events() -> list[NormalizedEvent]:
    return [
        make_event(
            i,
            event_id=f"{EVENT_ID}-{i}",
            timestamp=BASE + timedelta(seconds=i),
            user=USER,
            ip=IP if i % 2 else IPV6,
            host=HOST,
        )
        for i in range(6)
    ]


def _without_identity(vector_json: str) -> str:
    data = json.loads(vector_json)
    data.pop("event_id")
    return json.dumps(data)


def test_vectors_do_not_contain_the_ip_the_user_or_the_host() -> None:
    for vector in compute_features(_events(), history_start=HISTORY_START):
        text = _without_identity(vector.model_dump_json())
        for secret in (USER, IP, IPV6, HOST, "SENTINEL", "usr_", "192.0.2", "2001:db8"):
            assert secret not in text, secret
        assert "SENTINEL" not in repr(vector.features)


def test_the_event_id_only_appears_in_its_own_identity_field() -> None:
    vector = next(iter(compute_features(_events(), history_start=HISTORY_START)))
    assert vector.event_id.startswith(EVENT_ID)
    assert EVENT_ID not in str(dict(vector.features))
    assert EVENT_ID not in _without_identity(vector.model_dump_json())


def test_string_features_only_carry_catalog_values_or_the_source() -> None:
    catalog = {
        "event_type": {"authentication", "privilege_escalation", "other"},
        "action": {"login", "invalid_user", "sudo", "other"},
        "outcome": {"success", "failure", "unknown"},
        "source": {"linux-auth"},
    }
    for vector in compute_features(_events(), history_start=HISTORY_START):
        for name, value in vector.features.items():
            if isinstance(value, str):
                assert value in catalog[name], (name, value)
            else:
                assert isinstance(value, (int, float))


def test_the_schema_has_no_identifier_in_its_names_or_definitions() -> None:
    text = json.dumps(FEATURE_SCHEMA.model_dump()).lower()
    for secret in ("sentinel", USER, IP, "usr_"):
        assert secret.lower() not in text


@pytest.mark.parametrize(
    "code", ["invalid_history_start", "event_before_history", "unsorted_input", "duplicate_event"]
)
def test_errors_never_carry_data(code: str) -> None:
    error = FeatureError(code)  # type: ignore[arg-type]
    for text in (str(error), repr(error)):
        for secret in (USER, IP, HOST, "SENTINEL"):
            assert secret not in text


def test_a_failing_computation_does_not_leak_through_its_error() -> None:
    early = make_event(
        0, event_id=EVENT_ID, timestamp=BASE - timedelta(hours=2), user=USER, ip=IP, host=HOST
    )
    with pytest.raises(FeatureError) as caught:
        compute_event_features(early, [], history_start=HISTORY_START)
    for text in (str(caught.value), repr(caught.value)):
        assert EVENT_ID not in text and USER not in text and IP not in text and HOST not in text
