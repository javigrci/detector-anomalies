"""FR-003-22: valores ausentes deterministas con indicadores; ningún evento se descarta."""

from datetime import timedelta

from security_anomaly.features.pipeline import compute_features
from security_anomaly.features.schema import FEATURE_SCHEMA
from security_anomaly.schemas.event import NormalizedEvent, Outcome
from security_anomaly.schemas.features import FeatureVector
from tests.feature_factory import BASE, make_event, pseudonym, random_stream

HISTORY_START = BASE - timedelta(hours=1)
U1, U2 = pseudonym(1), pseudonym(2)
IP1, IP2 = "192.0.2.1", "192.0.2.2"


def _by_id(events: list[NormalizedEvent]) -> dict[str, FeatureVector]:
    return {v.event_id: v for v in compute_features(events, history_start=HISTORY_START)}


def _ev(
    i: int, *, user: str | None = None, ip: str | None = None, outcome: Outcome = Outcome.SUCCESS
) -> NormalizedEvent:
    return make_event(
        i,
        event_id=f"e{i}",
        timestamp=BASE + timedelta(seconds=i),
        user=user,
        ip=ip,
        outcome=outcome,
    )


def test_an_event_without_ip_has_zeroed_ip_features_and_the_indicator() -> None:
    vectors = _by_id([_ev(0, user=U1, ip=None, outcome=Outcome.FAILURE)])
    f = vectors["e0"].features
    assert (f["has_ip"], f["ip_event_count"], f["ip_failure_count"]) == (0, 0, 0)
    assert (f["ip_failure_rate"], f["ip_distinct_users"]) == (0.0, 0)
    assert f["has_user"] == 1


def test_an_event_without_user_has_zeroed_user_features_and_the_indicator() -> None:
    f = _by_id([_ev(0, user=None, ip=IP1)])["e0"].features
    assert (f["has_user"], f["user_distinct_ips"]) == (0, 0)
    assert (f["has_ip"], f["ip_event_count"]) == (1, 1)


def test_an_event_with_neither_has_the_fixed_shape_and_all_zeros() -> None:
    vector = _by_id([_ev(0, user=None, ip=None)])["e0"]
    assert tuple(vector.features) == FEATURE_SCHEMA.names
    window = ("ip_event_count", "ip_failure_count", "ip_failure_rate", "ip_distinct_users")
    assert all(vector.features[name] == 0 for name in window)
    assert (
        vector.features["user_distinct_ips"],
        vector.features["has_ip"],
        vector.features["has_user"],
    ) == (0, 0, 0)


def test_an_ip_event_without_user_counts_for_the_ip_but_not_for_its_distinct_users() -> None:
    vectors = _by_id([_ev(0, user=U1, ip=IP1), _ev(1, user=None, ip=IP1), _ev(2, user=U2, ip=IP1)])
    assert vectors["e1"].features["ip_event_count"] == 2
    assert vectors["e1"].features["ip_distinct_users"] == 1
    assert vectors["e2"].features["ip_distinct_users"] == 2


def test_a_user_event_without_ip_sees_the_ips_that_user_used_in_the_window() -> None:
    vectors = _by_id([_ev(0, user=U1, ip=IP1), _ev(1, user=U1, ip=IP2), _ev(2, user=U1, ip=None)])
    assert vectors["e2"].features["user_distinct_ips"] == 2
    assert vectors["e2"].features["ip_event_count"] == 0  # sin IP: sus agregadas por IP son 0


def test_no_event_is_dropped_whatever_fields_it_lacks() -> None:
    events = random_stream(4, 300, span_seconds=200, no_ip_rate=0.5, no_user_rate=0.5)
    assert any(e.source_ip is None for e in events) and any(
        e.user_pseudonym is None for e in events
    )
    out = list(compute_features(events, history_start=HISTORY_START))
    assert len(out) == len(events)
    assert all(tuple(v.features) == FEATURE_SCHEMA.names for v in out)
    for v in out:
        assert v.features["has_ip"] in (0, 1) and v.features["has_user"] in (0, 1)
