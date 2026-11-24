"""FR-003-18, 23: el esquema v1 coincide con `contracts/feature-schema.md`."""

from security_anomaly.features.schema import FEATURE_SCHEMA, FEATURE_SCHEMA_VERSION, WINDOW

EXPECTED = [
    ("hour_sin", "float", "event"),
    ("hour_cos", "float", "event"),
    ("day_of_week", "int", "event"),
    ("event_type", "category", "event"),
    ("action", "category", "event"),
    ("outcome", "category", "event"),
    ("source", "category", "event"),
    ("ip_event_count", "int", "window"),
    ("ip_failure_count", "int", "window"),
    ("ip_failure_rate", "float", "window"),
    ("ip_distinct_users", "int", "window"),
    ("user_distinct_ips", "int", "window"),
    ("has_ip", "int", "indicator"),
    ("has_user", "int", "indicator"),
]


def test_version_and_window() -> None:
    assert FEATURE_SCHEMA_VERSION == 1
    assert FEATURE_SCHEMA.version == FEATURE_SCHEMA_VERSION
    assert FEATURE_SCHEMA.window_seconds == 300
    assert WINDOW.total_seconds() == 300


def test_the_fourteen_features_in_contract_order() -> None:
    got = [(d.name, d.kind, d.scope) for d in FEATURE_SCHEMA.definitions]
    assert got == EXPECTED


def test_every_definition_is_documented() -> None:
    assert all(len(d.definition) >= 10 for d in FEATURE_SCHEMA.definitions)


def test_no_feature_is_named_like_an_identifier() -> None:
    forbidden = {"ip", "user", "host", "event_id", "source_ip", "user_pseudonym", "username"}
    assert not forbidden & set(FEATURE_SCHEMA.names)
