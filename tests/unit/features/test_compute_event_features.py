"""FR-003-17: un evento individual solo necesita la historia previa y nunca usa lo posterior."""

from collections.abc import Iterator
from datetime import timedelta

from security_anomaly.features.pipeline import compute_event_features
from security_anomaly.schemas.event import NormalizedEvent, Outcome
from tests.feature_factory import BASE, make_event, pseudonym

HISTORY_START = BASE - timedelta(hours=1)
IP = "192.0.2.1"


def _past(n: int) -> list[NormalizedEvent]:
    return [
        make_event(
            i,
            event_id=f"p{i:02d}",
            timestamp=BASE + timedelta(seconds=i),
            outcome=Outcome.FAILURE,
            user=pseudonym(1),
            ip=IP,
        )
        for i in range(n)
    ]


def _target() -> NormalizedEvent:
    return make_event(
        50, event_id="t", timestamp=BASE + timedelta(seconds=60), outcome=Outcome.FAILURE, ip=IP
    )


def test_the_vector_uses_the_previous_events_of_the_window() -> None:
    vector = compute_event_features(_target(), _past(5), history_start=HISTORY_START)
    assert vector.features["ip_event_count"] == 6
    assert vector.features["ip_failure_count"] == 6
    assert vector.features["ip_failure_rate"] == 1.0
    assert (vector.source, vector.event_id) == ("linux-auth", "t")


def test_later_events_in_the_history_are_ignored() -> None:
    future = [
        make_event(
            100 + i,
            event_id=f"z{i:02d}",
            timestamp=BASE + timedelta(seconds=61 + i),
            outcome=Outcome.FAILURE,
            ip=IP,
        )
        for i in range(30)
    ]
    base = compute_event_features(_target(), _past(5), history_start=HISTORY_START)
    with_future = compute_event_features(
        _target(),
        [*_past(5), *future],
        history_start=HISTORY_START,
    )
    assert with_future == base


def test_a_tie_that_sorts_after_the_event_is_ignored() -> None:
    same_instant_later = make_event(
        1, event_id="zzz", timestamp=BASE + timedelta(seconds=60), ip=IP
    )
    vector = compute_event_features(_target(), [same_instant_later], history_start=HISTORY_START)
    assert vector.features["ip_event_count"] == 1


def test_events_older_than_the_window_are_ignored() -> None:
    old = make_event(0, event_id="old", timestamp=BASE - timedelta(minutes=30), ip=IP)
    vector = compute_event_features(_target(), [old], history_start=HISTORY_START)
    assert vector.features["ip_event_count"] == 1


def test_an_empty_history_gives_a_valid_vector() -> None:
    vector = compute_event_features(_target(), [], history_start=HISTORY_START)
    assert vector.features["ip_event_count"] == 1
    assert list(vector.features)[:2] == ["hour_sin", "hour_cos"]


def test_the_event_itself_in_the_history_is_not_counted_twice() -> None:
    target = _target()
    vector = compute_event_features(target, [target, *_past(2)], history_start=HISTORY_START)
    assert vector.features["ip_event_count"] == 3


def test_the_history_is_not_modified_and_may_be_an_iterator() -> None:
    history = _past(5)
    snapshot = list(history)
    compute_event_features(_target(), history, history_start=HISTORY_START)
    assert history == snapshot

    def lazy() -> Iterator[NormalizedEvent]:
        yield from _past(5)

    vector = compute_event_features(_target(), lazy(), history_start=HISTORY_START)
    assert vector.features["ip_event_count"] == 6


def test_history_order_does_not_matter() -> None:
    forward = compute_event_features(_target(), _past(8), history_start=HISTORY_START)
    backward = compute_event_features(
        _target(), list(reversed(_past(8))), history_start=HISTORY_START
    )
    assert forward == backward
