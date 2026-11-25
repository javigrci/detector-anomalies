"""FR-004-01: el dataset solo acepta vectores con el esquema de características esperado."""

from datetime import UTC, datetime

import pytest

from security_anomaly.features.schema import FEATURE_SCHEMA
from security_anomaly.ml.dataset import make_dataset
from security_anomaly.ml.errors import MlError
from security_anomaly.schemas.features import FeatureVector
from tests.ml_factory import fake_vector

T0 = datetime(2026, 1, 5, tzinfo=UTC)


def _vector(**changes: object) -> FeatureVector:
    base = fake_vector(0, T0)
    data: dict[str, object] = {
        "source": base.source,
        "event_id": base.event_id,
        "timestamp": base.timestamp,
        "schema_version": base.schema_version,
        "context_complete": True,
        "features": dict(base.features),
    }
    data.update(changes)
    return FeatureVector.model_validate(data)


def test_valid_vectors_make_a_dataset_with_the_schema_identity() -> None:
    dataset = make_dataset([fake_vector(0, T0), fake_vector(1, T0)])
    assert dataset.schema_version == FEATURE_SCHEMA.version
    assert dataset.schema_fingerprint == FEATURE_SCHEMA.fingerprint
    assert len(dataset.vectors) == 2


def test_an_empty_dataset_is_allowed_to_exist() -> None:
    assert make_dataset([]).vectors == ()


@pytest.mark.parametrize(
    "bad",
    [
        _vector(schema_version=2),
        _vector(features={**fake_vector(0, T0).features, "extra": 1}),
        _vector(features={k: v for k, v in fake_vector(0, T0).features.items() if k != "has_ip"}),
        _vector(features=dict(reversed(list(fake_vector(0, T0).features.items())))),
    ],
)
def test_vectors_with_another_schema_are_rejected_without_values(bad: FeatureVector) -> None:
    with pytest.raises(MlError) as caught:
        make_dataset([fake_vector(1, T0), bad])
    assert caught.value.code == "invalid_schema"
    assert "fake-" not in f"{caught.value!s} {caught.value!r}"


def test_the_vectors_are_sorted_by_the_total_order() -> None:
    later = fake_vector(1, datetime(2026, 1, 6, tzinfo=UTC))
    earlier = fake_vector(2, T0)
    assert [v.event_id for v in make_dataset([later, earlier]).vectors] == [
        earlier.event_id,
        later.event_id,
    ]
