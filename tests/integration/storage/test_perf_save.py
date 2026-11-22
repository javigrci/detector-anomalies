"""SC-001: guardar un lote de 10.000 eventos y devolver su resumen en menos de 10 segundos."""

import os
import platform
import time

import pytest
from sqlalchemy import Engine, text

from security_anomaly.storage import save_events
from tests.storage_factory import make_events

pytestmark = pytest.mark.integration

VOLUME = 10_000
THRESHOLD_S = 10.0  # umbral de SC-001


def test_saving_ten_thousand_events_is_fast_enough(app_engine: Engine) -> None:
    events = make_events(VOLUME)
    started = time.perf_counter()
    summary = save_events(app_engine, events)
    elapsed = time.perf_counter() - started
    print(
        f"\n[SC-001] {VOLUME} eventos guardados: {elapsed:.3f} s (umbral {THRESHOLD_S} s) "
        f"| cpus={os.cpu_count()} os={platform.platform()} python={platform.python_version()} "
        "| PostgreSQL 16 en contenedor local"
    )
    assert summary.inserted == VOLUME
    with app_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM events")).scalar_one() == VOLUME
    assert elapsed < THRESHOLD_S

    started = time.perf_counter()
    again = save_events(app_engine, events)
    elapsed_again = time.perf_counter() - started
    print(f"[SC-001] reguardar el mismo lote (todo existente): {elapsed_again:.3f} s")
    assert (again.inserted, again.existing) == (0, VOLUME)
    assert elapsed_again < THRESHOLD_S
