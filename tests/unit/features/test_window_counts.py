"""FR-003-04…06, 08…10: las cinco agregadas por ventana."""

from datetime import datetime, timedelta

from security_anomaly.schemas.event import Outcome
from tests.feature_factory import BASE, make_event, pseudonym, run_engine

U1, U2, U3 = pseudonym(1), pseudonym(2), pseudonym(3)
IP1, IP2 = "192.0.2.1", "192.0.2.2"
F, S = Outcome.FAILURE, Outcome.SUCCESS


def _at(seconds: int) -> datetime:
    return BASE + timedelta(seconds=seconds)


def test_counts_grow_along_a_burst_from_one_ip() -> None:
    events = [
        make_event(i, event_id=f"b{i:02d}", timestamp=_at(i * 5), outcome=F, user=U1, ip=IP1)
        for i in range(10)
    ]
    result = run_engine(events)
    for i, event in enumerate(events):
        w = result[(event.source, event.event_id)]
        assert (w.ip_event_count, w.ip_failure_count, w.ip_failure_rate) == (i + 1, i + 1, 1.0)


def test_the_scored_event_counts_as_part_of_its_own_window() -> None:
    only = make_event(0, event_id="x", outcome=F, user=U1, ip=IP1)
    w = run_engine([only])[(only.source, only.event_id)]
    assert (w.ip_event_count, w.ip_failure_count, w.ip_failure_rate) == (1, 1, 1.0)
    ok = make_event(0, event_id="y", outcome=S, user=U1, ip=IP1)
    w = run_engine([ok])[(ok.source, ok.event_id)]
    assert (w.ip_event_count, w.ip_failure_count, w.ip_failure_rate) == (1, 0, 0.0)


def test_failure_rate_is_failures_over_events() -> None:
    events = [
        make_event(0, event_id="a", timestamp=_at(0), outcome=F, ip=IP1),
        make_event(1, event_id="b", timestamp=_at(1), outcome=S, ip=IP1),
        make_event(2, event_id="c", timestamp=_at(2), outcome=S, ip=IP1),
        make_event(3, event_id="d", timestamp=_at(3), outcome=F, ip=IP1),
    ]
    w = run_engine(events)[("linux-auth", "d")]
    assert (w.ip_event_count, w.ip_failure_count, w.ip_failure_rate) == (4, 2, 0.5)


def test_only_the_failure_outcome_counts_as_a_failure() -> None:
    events = [
        make_event(0, event_id="a", timestamp=_at(0), outcome=Outcome.UNKNOWN, ip=IP1),
        make_event(1, event_id="b", timestamp=_at(1), outcome=S, ip=IP1),
    ]
    assert run_engine(events)[("linux-auth", "b")].ip_failure_count == 0


def test_distinct_users_per_ip_counts_each_pseudonym_once_and_ignores_nulls() -> None:
    events = [
        make_event(0, event_id="a", timestamp=_at(0), user=U1, ip=IP1),
        make_event(1, event_id="b", timestamp=_at(1), user=U1, ip=IP1),
        make_event(2, event_id="c", timestamp=_at(2), user=U2, ip=IP1),
        make_event(3, event_id="d", timestamp=_at(3), user=None, ip=IP1),
        make_event(4, event_id="e", timestamp=_at(4), user=U3, ip=IP2),
    ]
    result = run_engine(events)
    assert result[("linux-auth", "d")].ip_distinct_users == 2
    assert result[("linux-auth", "e")].ip_distinct_users == 1


def test_distinct_ips_per_user() -> None:
    events = [
        make_event(0, event_id="a", timestamp=_at(0), user=U1, ip=IP1),
        make_event(1, event_id="b", timestamp=_at(1), user=U1, ip=IP1),
        make_event(2, event_id="c", timestamp=_at(2), user=U1, ip=IP2),
        make_event(3, event_id="d", timestamp=_at(3), user=U1, ip=None),
        make_event(4, event_id="e", timestamp=_at(4), user=U2, ip=IP1),
    ]
    result = run_engine(events)
    assert result[("linux-auth", "b")].user_distinct_ips == 1
    assert result[("linux-auth", "c")].user_distinct_ips == 2
    assert result[("linux-auth", "d")].user_distinct_ips == 2  # sin IP: ve las del usuario
    assert result[("linux-auth", "e")].user_distinct_ips == 1


def test_aggregates_are_per_source() -> None:
    events = [
        make_event(
            0, event_id="a", source="linux-auth", timestamp=_at(0), outcome=F, user=U1, ip=IP1
        ),
        make_event(1, event_id="a", source="win-sec", timestamp=_at(1), outcome=F, user=U1, ip=IP1),
        make_event(2, event_id="b", source="win-sec", timestamp=_at(2), outcome=F, user=U1, ip=IP2),
    ]
    result = run_engine(events)
    assert result[("linux-auth", "a")].ip_event_count == 1
    assert result[("win-sec", "a")].ip_event_count == 1  # la misma IP en otra fuente no se suma
    assert result[("win-sec", "b")].user_distinct_ips == 2
    assert result[("linux-auth", "a")].user_distinct_ips == 1


def test_hosts_of_the_same_source_are_added_together() -> None:
    events = [
        make_event(0, event_id="a", timestamp=_at(0), outcome=F, ip=IP1, host="srv-demo-01"),
        make_event(1, event_id="b", timestamp=_at(1), outcome=F, ip=IP1, host="srv-demo-02"),
        make_event(2, event_id="c", timestamp=_at(2), outcome=F, ip=IP1, host="srv-demo-03"),
    ]
    assert run_engine(events)[("linux-auth", "c")].ip_event_count == 3


def test_equivalent_ipv6_spellings_are_the_same_ip() -> None:
    events = [
        make_event(0, event_id="a", timestamp=_at(0), ip="2001:db8::1"),
        make_event(1, event_id="b", timestamp=_at(1), ip="2001:0db8:0000:0000:0000:0000:0000:0001"),
        make_event(2, event_id="c", timestamp=_at(2), ip="2001:DB8::1"),
    ]
    assert run_engine(events)[("linux-auth", "c")].ip_event_count == 3


def test_a_different_ip_does_not_add_to_the_window_of_another() -> None:
    events = [
        make_event(0, event_id="a", timestamp=_at(0), outcome=F, ip=IP1),
        make_event(1, event_id="b", timestamp=_at(1), outcome=F, ip=IP2),
    ]
    assert run_engine(events)[("linux-auth", "b")].ip_event_count == 1
