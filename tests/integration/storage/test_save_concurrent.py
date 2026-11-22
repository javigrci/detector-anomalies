"""FR-002-08, SC-002: guardados simultáneos con eventos solapados."""

import random
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, text

from security_anomaly.storage import save_events
from tests.storage_factory import make_events

pytestmark = pytest.mark.integration


def test_concurrent_overlapping_saves_store_each_event_once(app_engine: Engine) -> None:
    pool = make_events(400)

    def worker(seed: int) -> tuple[int, int]:
        rng = random.Random(seed)
        subset = rng.sample(pool, 300)  # claves solapadas y en distinto orden
        summary = save_events(app_engine, subset)
        return summary.inserted, summary.existing

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(worker, range(8)))

    with app_engine.connect() as connection:
        stored = connection.execute(text("SELECT count(*) FROM events")).scalar_one()
        distinct = connection.execute(
            text("SELECT count(DISTINCT (source, event_id)) FROM events")
        ).scalar_one()
    assert stored == distinct
    assert sum(inserted for inserted, _ in results) == stored
    assert all(inserted + existing == 300 for inserted, existing in results)


def test_same_batch_saved_concurrently_inserts_once(app_engine: Engine) -> None:
    events = make_events(500)
    with ThreadPoolExecutor(max_workers=6) as executor:
        summaries = list(executor.map(lambda _: save_events(app_engine, events), range(6)))
    assert sum(s.inserted for s in summaries) == 500
    assert sum(s.existing for s in summaries) == 500 * 5
