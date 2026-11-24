"""SC-008, FR-003-16: la memoria del streaming no crece con el tamaño del dataset."""

import tracemalloc
from collections.abc import Iterator
from datetime import timedelta

from security_anomaly.features.engine import FeatureEngine
from security_anomaly.features.pipeline import compute_features
from security_anomaly.schemas.event import NormalizedEvent, Outcome
from tests.feature_factory import BASE, make_event, pseudonym

HISTORY_START = BASE - timedelta(hours=1)
SMALL, LARGE = 10_000, 100_000


def _steady_stream(n: int) -> Iterator[NormalizedEvent]:
    """Un evento por segundo con la misma actividad concurrente, sea cual sea `n`."""
    for i in range(n):
        yield make_event(
            i,
            event_id=f"e{i:07d}",
            timestamp=BASE + timedelta(seconds=i),
            outcome=Outcome.FAILURE if i % 3 == 0 else Outcome.SUCCESS,
            user=pseudonym(i % 25),
            ip=f"192.0.2.{i % 60 + 1}",
        )


def _peak(n: int) -> int:
    tracemalloc.start()
    try:
        for _ in compute_features(_steady_stream(n), history_start=HISTORY_START, presorted=True):
            pass
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_peak_memory_does_not_grow_with_the_dataset() -> None:
    small, large = _peak(SMALL), _peak(LARGE)
    print(
        f"\n[SC-008] pico de memoria: {SMALL} eventos = {small / 1024:.0f} KiB, "
        f"{LARGE} eventos = {large / 1024:.0f} KiB (relación {large / small:.2f})"
    )
    assert large < 2 * small  # diez veces más datos, a lo sumo el doble de memoria


def test_the_window_state_empties_after_a_long_gap() -> None:
    engine = FeatureEngine()
    for event in _steady_stream(2000):
        engine.observe(event)
    assert 0 < engine.state_size <= 300  # un evento por segundo durante 5 minutos
    engine.observe(
        make_event(0, event_id="after-gap", timestamp=BASE + timedelta(days=1), ip="192.0.2.1")
    )
    assert engine.state_size == 1
