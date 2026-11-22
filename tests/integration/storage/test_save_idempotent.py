"""FR-002-07…09, 11, 19: guardado idempotente entre lotes y ejecuciones."""

import time
import uuid

import pytest
from sqlalchemy import Engine, text

from security_anomaly.schemas.event import Outcome
from security_anomaly.storage import save_events
from tests.storage_factory import make_event, make_events

pytestmark = pytest.mark.integration


def _count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM events")).scalar_one())


def test_first_save_inserts_everything(app_engine: Engine) -> None:
    summary = save_events(app_engine, make_events(50))
    assert (summary.inserted, summary.existing, summary.existing_with_different_content) == (
        50,
        0,
        0,
    )
    assert _count(app_engine) == 50


def test_saving_the_same_batch_again_adds_nothing(app_engine: Engine) -> None:
    events = make_events(50)
    save_events(app_engine, events)
    again = save_events(app_engine, events)
    assert (again.inserted, again.existing, again.existing_with_different_content) == (0, 50, 0)
    assert _count(app_engine) == 50


def test_overlapping_batches_store_shared_events_once(app_engine: Engine) -> None:
    first = save_events(app_engine, make_events(30, start=0))
    second = save_events(app_engine, make_events(30, start=15))
    assert first.inserted == 30
    assert (second.inserted, second.existing) == (15, 15)
    assert _count(app_engine) == 45


def test_same_key_with_different_content_keeps_the_original(app_engine: Engine) -> None:
    original = make_event(1, event_id="dup", host="srv-demo-01", outcome=Outcome.SUCCESS)
    save_events(app_engine, [original])
    changed = make_event(1, event_id="dup", host="srv-demo-99", outcome=Outcome.FAILURE)
    summary = save_events(app_engine, [changed, make_event(2, event_id="new")])
    assert (summary.inserted, summary.existing, summary.existing_with_different_content) == (
        1,
        1,
        1,
    )
    with app_engine.connect() as connection:
        row = connection.execute(
            text("SELECT host, outcome FROM events WHERE event_id = 'dup'")
        ).one()
    assert tuple(row) == ("srv-demo-01", "success")


def test_repeats_inside_the_input_count_as_existing(app_engine: Engine) -> None:
    a = make_event(1, event_id="same")
    summary = save_events(app_engine, [a, a, make_event(2, event_id="x")])
    assert (summary.inserted, summary.existing) == (2, 1)
    assert _count(app_engine) == 2


def test_ingested_at_does_not_change_when_saved_again(
    app_engine: Engine, migrator_engine: Engine
) -> None:
    events = make_events(5)
    save_events(app_engine, events)
    with migrator_engine.begin() as connection:
        connection.execute(text("UPDATE events SET ingested_at = now() - interval '30 days'"))
        before = connection.execute(
            text("SELECT min(ingested_at), max(ingested_at) FROM events")
        ).one()
    save_events(app_engine, events)
    with app_engine.connect() as connection:
        after = connection.execute(
            text("SELECT min(ingested_at), max(ingested_at) FROM events")
        ).one()
    assert tuple(before) == tuple(after)


def test_batch_id_is_stored_in_inserted_events_and_is_unique_per_save(app_engine: Engine) -> None:
    first = save_events(app_engine, make_events(5, start=0))
    second = save_events(app_engine, make_events(5, start=10))
    assert first.batch_id != second.batch_id
    with app_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT batch_id, count(*) FROM events GROUP BY batch_id")
        ).all()
    assert {(str(r[0]), r[1]) for r in rows} == {
        (str(first.batch_id), 5),
        (str(second.batch_id), 5),
    }


def test_explicit_batch_id_is_used(app_engine: Engine) -> None:
    batch = uuid.uuid4()
    summary = save_events(app_engine, make_events(3), batch_id=batch)
    assert summary.batch_id == batch


def test_a_save_that_inserts_nothing_leaves_no_trace(app_engine: Engine) -> None:
    events = make_events(5)
    save_events(app_engine, events)
    again = save_events(app_engine, events)
    with app_engine.connect() as connection:
        found = connection.execute(
            text("SELECT count(*) FROM events WHERE batch_id = :b"), {"b": again.batch_id}
        ).scalar_one()
    assert found == 0
    assert _count(app_engine) == 5


def test_a_batch_of_ten_thousand_is_saved_in_one_go(app_engine: Engine) -> None:
    events = make_events(10_000)
    started = time.perf_counter()
    summary = save_events(app_engine, events)
    elapsed = time.perf_counter() - started
    assert summary.inserted == 10_000
    assert _count(app_engine) == 10_000
    assert elapsed < 30  # medida real y umbral de SC-001 en test_perf_save.py
