"""SC-004: una consulta por rango de un día sobre 100.000 eventos responde en menos de 1 s."""

import os
import platform
import time
from datetime import timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.dialects import postgresql

from security_anomaly.storage import read_range, save_events
from security_anomaly.storage.events import build_range_statement
from tests.storage_factory import BASE_TIME, make_events

pytestmark = pytest.mark.integration

VOLUME = 100_000
THRESHOLD_S = 1.0  # umbral de SC-004


def test_one_day_range_over_one_hundred_thousand_events(
    app_engine: Engine, migrator_engine: Engine
) -> None:
    # 100.000 eventos repartidos en 30 días (≈ 3.333 por día).
    step = timedelta(days=30) / VOLUME
    for start in range(0, VOLUME, 10_000):
        save_events(app_engine, make_events(10_000, start=start, step=step))
    with migrator_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("ANALYZE events"))

    day_start = BASE_TIME + timedelta(days=10)
    day_end = day_start + timedelta(days=1)
    started = time.perf_counter()
    got = [e for chunk in read_range(app_engine, day_start, day_end) for e in chunk]
    elapsed = time.perf_counter() - started

    print(
        f"\n[SC-004] {VOLUME} eventos, 1 día ({len(got)} leídos): {elapsed:.3f} s "
        f"(umbral {THRESHOLD_S} s) | cpus={os.cpu_count()} cpu={platform.processor() or 'n/d'} "
        f"os={platform.platform()} python={platform.python_version()}"
    )
    assert 3000 < len(got) < 3700
    assert elapsed < THRESHOLD_S

    statement = build_range_statement(day_start, day_end, 5000, None)
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    compiled = statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    with app_engine.connect() as connection:
        plan = "\n".join(connection.execute(text("EXPLAIN " + str(compiled))).scalars())
    assert "ix_events_timestamp" in plan, plan
    assert "Seq Scan" not in plan, plan
