"""FR-003-18, 19: modelos del esquema y del vector de características."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from security_anomaly.schemas.features import FeatureDefinition, FeatureSchema, FeatureVector


def _definitions() -> tuple[FeatureDefinition, ...]:
    return (
        FeatureDefinition(name="a", kind="float", scope="event", definition="alfa"),
        FeatureDefinition(name="b", kind="int", scope="window", definition="beta"),
        FeatureDefinition(name="c", kind="category", scope="event", definition="gamma"),
    )


def _schema(**changes: object) -> FeatureSchema:
    base: dict[str, object] = {"version": 1, "window_seconds": 300, "definitions": _definitions()}
    base.update(changes)
    return FeatureSchema.model_validate(base)


def test_definition_validates_kind_and_scope() -> None:
    with pytest.raises(ValidationError):
        FeatureDefinition(name="x", kind="bool", scope="event", definition="d")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        FeatureDefinition(name="x", kind="int", scope="global", definition="d")  # type: ignore[arg-type]


def test_schema_names_follow_the_definitions_order() -> None:
    assert _schema().names == ("a", "b", "c")


def test_duplicate_names_are_rejected() -> None:
    dup = (*_definitions(), FeatureDefinition(name="a", kind="int", scope="event", definition="x"))
    with pytest.raises(ValidationError):
        _schema(definitions=dup)


def test_version_and_window_must_be_positive() -> None:
    for kwargs in ({"version": 0}, {"window_seconds": 0}):
        with pytest.raises(ValidationError):
            _schema(**kwargs)


def test_fingerprint_is_a_deterministic_sha256_hex() -> None:
    first = _schema().fingerprint
    assert first == _schema().fingerprint
    assert len(first) == 64 and int(first, 16) >= 0


def test_fingerprint_changes_with_every_part_of_the_schema() -> None:
    base = _schema().fingerprint
    d = _definitions()
    variants = [
        _schema(version=2),
        _schema(window_seconds=600),
        _schema(definitions=(d[1], d[0], d[2])),  # orden
        _schema(definitions=(d[0].model_copy(update={"name": "z"}), d[1], d[2])),  # nombre
        _schema(definitions=(d[0].model_copy(update={"kind": "int"}), d[1], d[2])),  # tipo
        _schema(definitions=(d[0].model_copy(update={"scope": "window"}), d[1], d[2])),  # ámbito
        _schema(definitions=(d[0].model_copy(update={"definition": "otra"}), d[1], d[2])),
        _schema(definitions=d[:2]),  # quitar
    ]
    assert all(v.fingerprint != base for v in variants)
    assert len({v.fingerprint for v in variants}) == len(variants)


def _vector(**changes: object) -> FeatureVector:
    base: dict[str, object] = {
        "source": "linux-auth",
        "event_id": "e1",
        "timestamp": datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=2))),
        "schema_version": 1,
        "context_complete": True,
        "features": {"a": 1.0, "b": 2, "c": "x"},
    }
    base.update(changes)
    return FeatureVector.model_validate(base)


def test_vector_timestamp_is_utc() -> None:
    vector = _vector()
    assert vector.timestamp == datetime(2026, 1, 1, 10, tzinfo=UTC)
    assert vector.timestamp.utcoffset() == timedelta(0)
    with pytest.raises(ValidationError):
        _vector(timestamp=datetime(2026, 1, 1))


def test_vector_is_immutable_including_its_features() -> None:
    vector = _vector()
    with pytest.raises(ValidationError):
        vector.context_complete = False
    with pytest.raises(TypeError):
        vector.features["a"] = 9.0  # type: ignore[index]


def test_vector_serializes_to_json_with_features_in_order() -> None:
    text = _vector().model_dump_json()
    assert text.index('"a"') < text.index('"b"') < text.index('"c"')


def test_equal_vectors_compare_equal() -> None:
    assert _vector() == _vector()
    assert _vector() != _vector(features={"a": 2.0, "b": 2, "c": "x"})
