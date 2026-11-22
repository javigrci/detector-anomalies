"""FR-002-21: la purga borra por bloques de 5.000, una transacción por bloque."""

import threading
import time

import pytest
from sqlalchemy import Engine, event, text

from security_anomaly.storage import purge_events, save_events
from tests.storage_factory import make_events

pytestmark = pytest.mark.integration

VOLUME = 12_000


def _prepare(app_engine: Engine, migrator_engine: Engine) -> None:
    for start in range(0, VOLUME, 6000):
        save_events(app_engine, make_events(6000, start=start))
    with migrator_engine.begin() as connection:
        connection.execute(text("UPDATE events SET ingested_at = now() - interval '200 days'"))


def test_many_candidates_are_deleted_in_several_transactions(
    app_engine: Engine, migrator_engine: Engine, maint_engine: Engine
) -> None:
    _prepare(app_engine, migrator_engine)
    commits: list[int] = []

    def on_commit(_connection: object) -> None:
        commits.append(1)

    event.listen(maint_engine, "commit", on_commit)
    try:
        result = purge_events(maint_engine, retention_days=90)
    finally:
        event.remove(maint_engine, "commit", on_commit)
    assert result.affected == VOLUME
    assert len(commits) >= 3  # 12.000 filas en bloques de 5.000 → 5.000 + 5.000 + 2.000
    with app_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM events")).scalar_one() == 0


def test_other_connections_are_not_blocked_while_it_runs(
    app_engine: Engine, migrator_engine: Engine, maint_engine: Engine
) -> None:
    _prepare(app_engine, migrator_engine)
    worst = 0.0
    done = threading.Event()

    def purge() -> None:
        try:
            purge_events(maint_engine, retention_days=90)
        finally:
            done.set()

    thread = threading.Thread(target=purge)
    thread.start()
    index = VOLUME
    while not done.is_set():
        started = time.perf_counter()
        save_events(app_engine, make_events(1, start=index))
        with app_engine.connect() as connection:
            connection.execute(text("SELECT count(*) FROM events WHERE host = 'srv-demo-01'"))
        worst = max(worst, time.perf_counter() - started)
        index += 1
    thread.join()
    assert worst < 2.0
