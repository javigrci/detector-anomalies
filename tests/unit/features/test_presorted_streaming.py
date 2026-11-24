"""FR-003-16, 25: el modo `presorted` procesa en streaming y verifica el orden."""

from collections.abc import Iterator
from datetime import timedelta

import pytest

from security_anomaly.features.engine import event_order_key
from security_anomaly.features.errors import FeatureError
from security_anomaly.features.pipeline import compute_features
from security_anomaly.schemas.event import NormalizedEvent
from tests.feature_factory import BASE, make_event, random_stream

HISTORY_START = BASE - timedelta(hours=1)


def test_it_consumes_the_input_lazily() -> None:
    events = sorted(random_stream(1, 500, span_seconds=400), key=event_order_key)
    consumed = 0

    def source() -> Iterator[NormalizedEvent]:
        nonlocal consumed
        for event in events:
            consumed += 1
            yield event

    stream = compute_features(source(), history_start=HISTORY_START, presorted=True)
    next(stream)
    assert consumed <= 2  # no se ha leído el resto
    rest = list(stream)
    assert consumed == 500 and len(rest) == 499


def test_it_gives_the_same_vectors_as_the_default_mode() -> None:
    events = sorted(random_stream(2, 800, span_seconds=600), key=event_order_key)
    assert list(compute_features(events, history_start=HISTORY_START, presorted=True)) == list(
        compute_features(events, history_start=HISTORY_START)
    )


def test_an_unsorted_input_is_a_controlled_error_without_values() -> None:
    late = make_event(1, event_id="SENTINEL-ID-late", timestamp=BASE + timedelta(seconds=10))
    early = make_event(0, event_id="SENTINEL-ID-early", timestamp=BASE)
    with pytest.raises(FeatureError) as caught:
        list(compute_features([late, early], history_start=HISTORY_START, presorted=True))
    assert caught.value.code == "unsorted_input"
    assert "SENTINEL" not in f"{caught.value!s} {caught.value!r}"


def test_a_repeated_event_in_streaming_mode_is_a_controlled_error() -> None:
    event = make_event(0, event_id="dup")
    with pytest.raises(FeatureError) as caught:
        list(compute_features([event, event], history_start=HISTORY_START, presorted=True))
    assert caught.value.code == "duplicate_event"


def test_an_empty_input_gives_no_vectors() -> None:
    assert list(compute_features([], history_start=HISTORY_START, presorted=True)) == []
