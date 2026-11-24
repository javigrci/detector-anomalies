"""FR-003-04, 05, 07: el motor coincide con el oráculo de referencia en flujos generados."""

import pytest

from tests.feature_factory import random_stream, reference_window, run_engine


@pytest.mark.parametrize("seed", range(30))
def test_engine_matches_the_reference(seed: int) -> None:
    events = random_stream(seed, 90, span_seconds=700, n_users=5)
    result = run_engine(events)
    for event in events:
        got = result[(event.source, event.event_id)]
        want = reference_window(events, event)
        assert got.ip_event_count == want["ip_event_count"]
        assert got.ip_failure_count == want["ip_failure_count"]
        assert got.ip_failure_rate == want["ip_failure_rate"]
        assert got.ip_distinct_users == want["ip_distinct_users"]
        assert got.user_distinct_ips == want["user_distinct_ips"]


def test_it_also_matches_with_several_sources_and_dense_ties() -> None:
    events = random_stream(99, 120, sources=("linux-auth", "win-sec"), span_seconds=40)
    result = run_engine(events)
    for event in events:
        got = result[(event.source, event.event_id)]
        want = reference_window(events, event)
        assert got.ip_event_count == want["ip_event_count"]
        assert got.user_distinct_ips == want["user_distinct_ips"]
