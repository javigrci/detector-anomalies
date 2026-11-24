"""SC-005: 100.000 eventos en menos de 60 s y un evento individual en menos de 100 ms (p95)."""

import os
import platform
import statistics
import time
from bisect import bisect_left
from datetime import timedelta

from security_anomaly.features.engine import event_order_key
from security_anomaly.features.pipeline import compute_event_features, compute_features
from tests.feature_factory import BASE, WINDOW, random_stream

VOLUME = 100_000
BATCH_THRESHOLD_S = 60.0  # umbral de SC-005
SINGLE_P95_THRESHOLD_S = 0.100  # umbral de SC-005
HISTORY_START = BASE - timedelta(hours=1)


def _environment() -> str:
    return (
        f"cpus={os.cpu_count()} os={platform.platform()} python={platform.python_version()} "
        "| máquina de desarrollo (WSL2), sin otras cargas controladas"
    )


def test_one_hundred_thousand_events_in_under_a_minute() -> None:
    events = sorted(
        random_stream(7, VOLUME, span_seconds=6 * 3600, n_users=40, mixed_zones=False),
        key=event_order_key,
    )
    started = time.perf_counter()
    count = sum(1 for _ in compute_features(events, history_start=HISTORY_START, presorted=True))
    elapsed = time.perf_counter() - started
    print(
        f"\n[SC-005] {VOLUME} eventos: {elapsed:.2f} s (umbral {BATCH_THRESHOLD_S} s) "
        f"| {_environment()}"
    )
    assert count == VOLUME
    assert elapsed < BATCH_THRESHOLD_S


def test_a_single_event_with_its_five_minute_history_is_fast() -> None:
    events = sorted(
        random_stream(9, 20_000, span_seconds=3600, mixed_zones=False), key=event_order_key
    )
    instants = [event_order_key(e)[0] for e in events]
    timings: list[float] = []
    for index in range(5000, 5000 + 300):
        first = bisect_left(instants, instants[index] - WINDOW)
        history = events[first:index]
        started = time.perf_counter()
        compute_event_features(events[index], history, history_start=HISTORY_START)
        timings.append(time.perf_counter() - started)
    p95 = statistics.quantiles(timings, n=100)[94]
    print(
        f"\n[SC-005] evento individual (historia de {len(history)} eventos): "
        f"p95 {p95 * 1000:.2f} ms, máx {max(timings) * 1000:.2f} ms "
        f"(umbral {SINGLE_P95_THRESHOLD_S * 1000:.0f} ms) | {_environment()}"
    )
    assert p95 < SINGLE_P95_THRESHOLD_S
