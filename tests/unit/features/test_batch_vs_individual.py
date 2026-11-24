"""SC-002, FR-003-15: el cálculo por lotes y el de un evento individual dan el mismo vector."""

from bisect import bisect_left
from datetime import timedelta

from security_anomaly.features.engine import event_order_key
from security_anomaly.features.pipeline import compute_event_features, compute_features
from tests.feature_factory import BASE, WINDOW, random_stream

HISTORY_START = BASE - timedelta(hours=1)


def test_batch_and_individual_vectors_are_identical_on_five_thousand_events() -> None:
    events = sorted(random_stream(21, 5000, span_seconds=3600), key=event_order_key)
    batch = {
        (v.source, v.event_id): v for v in compute_features(events, history_start=HISTORY_START)
    }
    assert len(batch) == 5000
    instants = [event_order_key(e)[0] for e in events]
    for index, event in enumerate(events):
        first = bisect_left(instants, instants[index] - WINDOW - timedelta(seconds=1))
        # La historia aportada incluye los de la ventana y, a propósito, algunos posteriores.
        history = [*events[first:index], *events[index + 1 : index + 15]]
        single = compute_event_features(event, history, history_start=HISTORY_START)
        assert single == batch[(event.source, event.event_id)], event.event_id


def test_the_two_paths_agree_with_several_sources_and_dense_ties() -> None:
    events = sorted(
        random_stream(5, 600, sources=("linux-auth", "win-sec"), span_seconds=60),
        key=event_order_key,
    )
    batch = {
        (v.source, v.event_id): v for v in compute_features(events, history_start=HISTORY_START)
    }
    for index, event in enumerate(events):
        single = compute_event_features(event, events[:index], history_start=HISTORY_START)
        assert single == batch[(event.source, event.event_id)]


def test_vectors_follow_the_total_order() -> None:
    events = random_stream(8, 300, span_seconds=200)
    out = list(compute_features(events, history_start=HISTORY_START))
    assert [(v.source, v.event_id) for v in out] == [
        (e.source, e.event_id) for e in sorted(events, key=event_order_key)
    ]
