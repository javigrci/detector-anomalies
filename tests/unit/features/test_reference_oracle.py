"""El oráculo de referencia da los valores esperados en un caso pequeño calculado a mano."""

from datetime import UTC, datetime, timedelta

from security_anomaly.schemas.event import Outcome
from tests.feature_factory import BASE, make_event, pseudonym, random_stream, reference_features
from tests.feature_factory import reference_window as window

U1, U2 = pseudonym(1), pseudonym(2)


def _case() -> list:  # type: ignore[type-arg]
    return [
        make_event(
            0, event_id="a", timestamp=BASE, outcome=Outcome.FAILURE, user=U1, ip="192.0.2.1"
        ),
        make_event(
            1,
            event_id="b",
            timestamp=BASE + timedelta(seconds=60),
            outcome=Outcome.SUCCESS,
            user=U2,
            ip="192.0.2.1",
        ),
        make_event(
            2,
            event_id="c",
            timestamp=BASE + timedelta(seconds=120),
            outcome=Outcome.FAILURE,
            user=U1,
            ip="192.0.2.9",
        ),
        make_event(3, event_id="d", timestamp=BASE + timedelta(seconds=400), ip="192.0.2.1"),
    ]


def test_hand_computed_windows() -> None:
    a, b, c, d = _case()
    events = [a, b, c, d]
    assert window(events, a) == {
        "ip_event_count": 1,
        "ip_failure_count": 1,
        "ip_failure_rate": 1.0,
        "ip_distinct_users": 1,
        "user_distinct_ips": 1,
    }
    assert window(events, b)["ip_event_count"] == 2
    assert window(events, b)["ip_failure_rate"] == 0.5
    assert window(events, b)["ip_distinct_users"] == 2
    assert window(events, c)["user_distinct_ips"] == 2  # U1 vio 192.0.2.1 y 192.0.2.9
    # `a` y `b` quedan fuera de la ventana de `d` (400 s > 300 s); solo cuenta `d` y `c` (otra IP).
    assert window(events, d) == {
        "ip_event_count": 1,
        "ip_failure_count": 0,
        "ip_failure_rate": 0.0,
        "ip_distinct_users": 0,
        "user_distinct_ips": 0,
    }


def test_reference_features_include_indicators_and_context() -> None:
    a, *_ = _case()
    features, complete = reference_features(_case(), a, BASE - timedelta(minutes=5))
    assert features["has_ip"] == 1 and features["has_user"] == 1
    assert complete is True
    _, incomplete = reference_features(_case(), a, BASE)
    assert incomplete is False


def test_random_stream_is_reproducible_and_has_ties() -> None:
    assert random_stream(7, 300) == random_stream(7, 300)
    stamps = [e.timestamp.astimezone(UTC) for e in random_stream(7, 300)]
    assert len(set(stamps)) < len(stamps)
    assert all(isinstance(s, datetime) for s in stamps)
