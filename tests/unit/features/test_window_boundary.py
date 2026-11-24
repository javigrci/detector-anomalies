"""FR-003-07: la ventana es `(t - 5 min, t]`; el borde inferior es exclusivo."""

from datetime import timedelta

from tests.feature_factory import BASE, make_event, run_engine

IP = "192.0.2.1"
FIVE = timedelta(minutes=5)


def _count(old_offset: timedelta) -> int:
    old = make_event(0, event_id="a-old", timestamp=BASE, ip=IP)
    now = make_event(1, event_id="b-now", timestamp=BASE + old_offset, ip=IP)
    return int(run_engine([old, now])[("linux-auth", "b-now")].ip_event_count)


def test_an_event_exactly_five_minutes_before_does_not_count() -> None:
    assert _count(FIVE) == 1


def test_an_event_one_microsecond_inside_the_window_counts() -> None:
    assert _count(FIVE - timedelta(microseconds=1)) == 2


def test_an_event_one_microsecond_outside_the_window_does_not_count() -> None:
    assert _count(FIVE + timedelta(microseconds=1)) == 1


def test_an_event_at_the_same_instant_counts() -> None:
    assert _count(timedelta(0)) == 2


def test_an_empty_window_still_contains_the_event_itself() -> None:
    lone = make_event(0, event_id="lone", ip=IP)
    assert run_engine([lone])[("linux-auth", "lone")].ip_event_count == 1


def test_a_gap_longer_than_five_minutes_does_not_carry_earlier_activity() -> None:
    burst = [
        make_event(i, event_id=f"b{i}", timestamp=BASE + timedelta(seconds=i), ip=IP)
        for i in range(20)
    ]
    after = make_event(99, event_id="after", timestamp=BASE + timedelta(minutes=30), ip=IP)
    result = run_engine([*burst, after])
    assert result[("linux-auth", "b19")].ip_event_count == 20
    assert result[("linux-auth", "after")].ip_event_count == 1


def test_old_users_and_ips_leave_the_distinct_counts() -> None:
    from tests.feature_factory import pseudonym

    a = make_event(0, event_id="a", timestamp=BASE, user=pseudonym(1), ip="192.0.2.1")
    b = make_event(
        1, event_id="b", timestamp=BASE + timedelta(minutes=4), user=pseudonym(1), ip="192.0.2.2"
    )
    c = make_event(
        2, event_id="c", timestamp=BASE + timedelta(minutes=6), user=pseudonym(1), ip="192.0.2.3"
    )
    result = run_engine([a, b, c])
    assert result[("linux-auth", "b")].user_distinct_ips == 2
    assert result[("linux-auth", "c")].user_distinct_ips == 2  # `a` ya salió; quedan b y c
