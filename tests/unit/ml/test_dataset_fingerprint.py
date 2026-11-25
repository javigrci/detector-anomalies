"""FR-004-05: huella determinista del dataset, sensible a cualquier cambio."""

import random

from security_anomaly.ml.dataset import dataset_fingerprint, make_dataset
from security_anomaly.schemas.features import FeatureVector
from tests.ml_factory import synthetic_vectors, tweak


def _fp(vectors: list[FeatureVector]) -> str:
    return dataset_fingerprint(make_dataset(vectors))


def test_it_is_a_deterministic_sha256_hex() -> None:
    vectors = synthetic_vectors(1, 400).vectors
    first = _fp(vectors)
    assert first == _fp(vectors)
    assert len(first) == 64 and int(first, 16) >= 0


def test_it_does_not_depend_on_the_input_order() -> None:
    vectors = synthetic_vectors(1, 400).vectors
    shuffled = list(vectors)
    random.Random(1).shuffle(shuffled)
    assert _fp(shuffled) == _fp(vectors)


def test_one_changed_value_one_changed_identifier_or_one_missing_vector_changes_it() -> None:
    vectors = synthetic_vectors(1, 400).vectors
    base = _fp(vectors)
    value = [tweak(vectors[0], ip_event_count=999), *vectors[1:]]
    assert _fp(value) != base
    category = [tweak(vectors[0], outcome="unknown-x"), *vectors[1:]]
    assert _fp(category) != base
    ident = vectors[0].model_copy(update={"event_id": "other-id"})
    assert _fp([ident, *vectors[1:]]) != base
    assert _fp(vectors[:-1]) != base
    assert _fp(vectors[1:]) != base


def test_a_tiny_float_difference_changes_it() -> None:
    vectors = synthetic_vectors(2, 300).vectors
    nudged = [
        tweak(vectors[0], hour_sin=float(vectors[0].features["hour_sin"]) + 1e-12),
        *vectors[1:],
    ]
    assert _fp(nudged) != _fp(vectors)


def test_different_datasets_have_different_fingerprints() -> None:
    assert _fp(synthetic_vectors(1, 300).vectors) != _fp(synthetic_vectors(2, 300).vectors)


def test_the_fingerprint_never_contains_identifiers() -> None:
    vectors = synthetic_vectors(1, 200).vectors
    text = _fp(vectors)
    for vector in vectors[:20]:
        assert vector.event_id not in text
