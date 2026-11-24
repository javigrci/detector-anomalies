"""SC-003, FR-003-12: el orden de llegada de la entrada no cambia ningún vector."""

import random
from datetime import timedelta

import pytest

from security_anomaly.features.errors import FeatureError
from security_anomaly.features.pipeline import compute_features
from tests.feature_factory import BASE, make_event, random_stream

HISTORY_START = BASE - timedelta(hours=1)


@pytest.mark.parametrize("seed", range(8))
def test_shuffled_inputs_give_identical_vectors(seed: int) -> None:
    events = random_stream(seed, 400, span_seconds=500)
    expected = list(compute_features(events, history_start=HISTORY_START))
    rng = random.Random(seed)
    for _ in range(3):
        shuffled = list(events)
        rng.shuffle(shuffled)
        assert list(compute_features(shuffled, history_start=HISTORY_START)) == expected


def test_reversed_input_gives_identical_vectors() -> None:
    events = random_stream(3, 300, span_seconds=300)
    assert list(compute_features(reversed(events), history_start=HISTORY_START)) == list(
        compute_features(events, history_start=HISTORY_START)
    )


def test_a_repeated_event_is_a_controlled_error() -> None:
    event = make_event(0, event_id="dup")
    with pytest.raises(FeatureError) as caught:
        list(compute_features([event, event], history_start=HISTORY_START))
    assert caught.value.code == "duplicate_event"


def test_an_empty_input_gives_no_vectors() -> None:
    assert list(compute_features([], history_start=HISTORY_START)) == []
