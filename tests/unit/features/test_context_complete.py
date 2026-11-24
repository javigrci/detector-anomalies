"""FR-003-14: `context_complete` = `timestamp - 5 min >= history_start` (lo declara quien llama)."""

from datetime import timedelta

import pytest

from security_anomaly.features.pipeline import compute_event_features, compute_features
from tests.feature_factory import BASE, WINDOW, make_event, random_stream, reference_features

IP = "192.0.2.1"
EVENT_TIME = BASE + timedelta(minutes=30)


def _complete(history_start: object) -> bool:
    event = make_event(0, event_id="x", timestamp=EVENT_TIME, ip=IP)
    return compute_event_features(event, [], history_start=history_start).context_complete  # type: ignore[arg-type]


def test_the_boundary_is_inclusive() -> None:
    assert _complete(EVENT_TIME - WINDOW) is True


def test_one_microsecond_short_of_the_window_is_incomplete() -> None:
    assert _complete(EVENT_TIME - WINDOW + timedelta(microseconds=1)) is False


def test_an_older_history_is_complete_and_a_later_one_incomplete() -> None:
    assert _complete(EVENT_TIME - timedelta(hours=3)) is True
    assert _complete(EVENT_TIME) is False


def test_an_empty_window_covered_by_the_history_is_complete() -> None:
    event = make_event(0, event_id="x", timestamp=EVENT_TIME, ip=IP)
    vector = compute_event_features(event, [], history_start=EVENT_TIME - timedelta(hours=1))
    assert vector.features["ip_event_count"] == 1
    assert vector.context_complete is True


def test_the_first_event_of_a_range_is_incomplete_when_history_starts_at_it() -> None:
    events = [make_event(i, timestamp=BASE + timedelta(seconds=i * 60), ip=IP) for i in range(10)]
    vectors = list(compute_features(events, history_start=BASE))
    flags = [v.context_complete for v in vectors]
    assert flags[0] is False and flags[4] is False  # +4 min: la ventana aún empieza antes
    assert flags[5] is True  # +5 min: t - 5 min == history_start
    assert flags[-1] is True


def test_the_flag_does_not_depend_on_the_events_in_the_history() -> None:
    event = make_event(0, event_id="x", timestamp=EVENT_TIME, ip=IP)
    history = [make_event(1, event_id="a", timestamp=EVENT_TIME - timedelta(seconds=30), ip=IP)]
    start = EVENT_TIME - timedelta(minutes=2)
    assert (
        compute_event_features(event, [], history_start=start).context_complete
        == compute_event_features(event, history, history_start=start).context_complete
        is False
    )


@pytest.mark.parametrize("seed", range(5))
def test_flag_and_features_match_the_reference(seed: int) -> None:
    history_start = BASE + timedelta(seconds=120)
    events = [e for e in random_stream(seed, 80, span_seconds=600) if e.timestamp >= history_start]
    for vector in compute_features(events, history_start=history_start):
        target = next(
            e for e in events if (e.source, e.event_id) == (vector.source, vector.event_id)
        )
        features, complete = reference_features(events, target, history_start)
        assert vector.context_complete is complete
        assert dict(vector.features) == features
