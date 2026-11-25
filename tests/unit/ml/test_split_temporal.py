"""FR-004-02…04: separación temporal contigua, sin solapes y con empates juntos."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from security_anomaly.ml.dataset import make_dataset, split_temporal
from security_anomaly.ml.errors import MlError
from security_anomaly.schemas.features import FeatureVector
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import fake_vector, synthetic_vectors

T0 = datetime(2026, 1, 5, tzinfo=UTC)


def _line(n: int) -> list[FeatureVector]:
    return [fake_vector(i, T0 + timedelta(seconds=i)) for i in range(n)]


def test_three_contiguous_ordered_blocks_that_cover_everything() -> None:
    dataset = make_dataset(synthetic_vectors(1, 1000).vectors)
    part = split_temporal(dataset, MlPolicy())
    ids = [v.event_id for v in (*part.train, *part.calibration, *part.test)]
    assert ids == [v.event_id for v in dataset.vectors]
    assert part.train[-1].timestamp <= part.calibration[0].timestamp
    assert part.calibration[-1].timestamp <= part.test[0].timestamp
    assert len(set(ids)) == len(ids)  # un evento nunca cae en dos conjuntos


def test_default_proportions_are_seventy_fifteen_fifteen() -> None:
    part = split_temporal(make_dataset(_line(1000)), MlPolicy())
    assert (len(part.train), len(part.calibration), len(part.test)) == (700, 150, 150)


def test_fractions_are_configurable() -> None:
    policy = MlPolicy(train_fraction=0.5, calibration_fraction=0.25, min_events_per_set=10)
    part = split_temporal(make_dataset(_line(400)), policy)
    assert (len(part.train), len(part.calibration), len(part.test)) == (200, 100, 100)


def test_the_oldest_data_trains_and_the_newest_tests() -> None:
    part = split_temporal(make_dataset(_line(1000)), MlPolicy())
    assert part.train[0].event_id == "fake-000000"
    assert part.test[-1].event_id == "fake-000999"


def test_events_with_the_same_timestamp_stay_in_the_same_set() -> None:
    # 100 instantes con 10 eventos cada uno: la frontera exacta (700) cae al inicio de un instante.
    vectors = [fake_vector(i, T0 + timedelta(seconds=i // 10)) for i in range(1000)]
    # Una frontera que caería a mitad de un instante: se desplaza al siguiente instante distinto.
    vectors = (
        vectors[:695]
        + [fake_vector(i, T0 + timedelta(seconds=69)) for i in range(695, 705)]
        + vectors[705:]
    )
    part = split_temporal(make_dataset(vectors), MlPolicy())
    sets = [{v.timestamp for v in s} for s in (part.train, part.calibration, part.test)]
    assert not (sets[0] & sets[1]) and not (sets[1] & sets[2]) and not (sets[0] & sets[2])


def test_a_dataset_below_the_minimum_is_rejected_with_a_controlled_error() -> None:
    with pytest.raises(MlError) as caught:
        split_temporal(make_dataset(_line(50)), MlPolicy())
    assert caught.value.code == "insufficient_data"
    assert "SENTINEL" not in str(caught.value)


def test_an_empty_dataset_is_rejected() -> None:
    with pytest.raises(MlError) as caught:
        split_temporal(make_dataset([]), MlPolicy())
    assert caught.value.code == "insufficient_data"


def test_all_events_at_the_same_instant_cannot_be_split() -> None:
    same = [fake_vector(i, T0) for i in range(1000)]
    with pytest.raises(MlError) as caught:
        split_temporal(make_dataset(same), MlPolicy())
    assert caught.value.code == "insufficient_data"


def test_the_minimum_is_per_set_and_configurable() -> None:
    policy = MlPolicy(min_events_per_set=200)
    with pytest.raises(MlError):
        split_temporal(make_dataset(_line(1000)), policy)  # calibración y prueba de 150 < 200
    ok = split_temporal(make_dataset(_line(1500)), policy)
    assert len(ok.calibration) >= 200


def test_the_partition_carries_the_schema_of_the_dataset() -> None:
    dataset = make_dataset(_line(1000))
    part = split_temporal(dataset, MlPolicy())
    assert (part.schema_version, part.schema_fingerprint) == (
        dataset.schema_version,
        dataset.schema_fingerprint,
    )
    assert replace(part, test=()).test == ()
