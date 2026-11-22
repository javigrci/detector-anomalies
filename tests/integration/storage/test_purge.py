"""FR-002-19…21, SC-005: la purga cuenta desde la ingesta, es explícita y repetible."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from security_anomaly.storage import StoragePolicy, purge_events, save_events
from tests.storage_factory import make_event, make_events

pytestmark = pytest.mark.integration


def _count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM events")).scalar_one())


def _age(migrator_engine: Engine, event_ids: list[str], days: int) -> None:
    with migrator_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE events SET ingested_at = now() - make_interval(days => :d) "
                "WHERE event_id = ANY(:ids)"
            ),
            {"d": days, "ids": event_ids},
        )


@pytest.fixture
def aged(app_engine: Engine, migrator_engine: Engine) -> Engine:
    events = make_events(30)
    save_events(app_engine, events)
    _age(migrator_engine, [e.event_id for e in events[:10]], 100)  # más viejos que 90 días
    _age(migrator_engine, [e.event_id for e in events[10:20]], 50)  # dentro del periodo
    return app_engine  # los 10 últimos acaban de ingerirse


def test_only_events_older_than_the_period_are_deleted(aged: Engine, maint_engine: Engine) -> None:
    result = purge_events(maint_engine, retention_days=90)
    assert (result.affected, result.dry_run, result.retention_days) == (10, False, 90)
    assert _count(aged) == 20
    with aged.connect() as connection:
        left = set(connection.execute(text("SELECT event_id FROM events")).scalars())
    assert not any(f"evt-{i:06d}" in left for i in range(10))


def test_dry_run_reports_without_deleting(aged: Engine, maint_engine: Engine) -> None:
    result = purge_events(maint_engine, retention_days=90, dry_run=True)
    assert (result.affected, result.dry_run) == (10, True)
    assert _count(aged) == 30


def test_the_default_period_is_ninety_days(aged: Engine, maint_engine: Engine) -> None:
    assert purge_events(maint_engine).retention_days == 90
    assert _count(aged) == 20


def test_the_period_can_come_from_the_policy(aged: Engine, maint_engine: Engine) -> None:
    result = purge_events(maint_engine, policy=StoragePolicy(retention_days=30))
    assert result.retention_days == 30
    assert result.affected == 20
    assert _count(aged) == 10


def test_nothing_is_deleted_automatically(aged: Engine) -> None:
    save_events(aged, make_events(5, start=100))
    assert _count(aged) == 35  # guardar o consultar nunca purga


def test_repeating_the_purge_deletes_nothing_and_does_not_fail(
    aged: Engine, maint_engine: Engine
) -> None:
    first = purge_events(maint_engine, retention_days=90)
    second = purge_events(maint_engine, retention_days=90)
    assert (first.affected, second.affected) == (10, 0)


@pytest.mark.parametrize("days", [0, -1])
def test_a_non_positive_period_is_rejected_without_deleting(
    aged: Engine, maint_engine: Engine, days: int
) -> None:
    with pytest.raises(ValueError, match="retention_days"):
        purge_events(maint_engine, retention_days=days)
    assert _count(aged) == 30


def test_a_period_longer_than_every_event_deletes_nothing(
    aged: Engine, maint_engine: Engine
) -> None:
    assert purge_events(maint_engine, retention_days=10_000).affected == 0
    assert _count(aged) == 30


def test_old_timestamps_just_ingested_are_not_purged(
    app_engine: Engine, maint_engine: Engine
) -> None:
    ancient = datetime(2001, 1, 1, tzinfo=UTC)
    save_events(
        app_engine,
        [
            make_event(i, event_id=f"old-{i}", timestamp=ancient + timedelta(days=i))
            for i in range(5)
        ],
    )
    assert purge_events(maint_engine, retention_days=1).affected == 0
    assert _count(app_engine) == 5


def test_saving_an_existing_event_again_does_not_restart_its_retention(
    app_engine: Engine, migrator_engine: Engine, maint_engine: Engine
) -> None:
    events = make_events(3)
    save_events(app_engine, events)
    _age(migrator_engine, [e.event_id for e in events], 100)
    save_events(app_engine, events)  # reingesta
    assert purge_events(maint_engine, retention_days=90).affected == 3


def test_now_is_only_a_calculation_input(aged: Engine, maint_engine: Engine) -> None:
    far_future = datetime.now(UTC) + timedelta(days=365)
    result = purge_events(maint_engine, retention_days=90, now=far_future, dry_run=True)
    assert result.affected == 30
    assert result.cutoff == far_future - timedelta(days=90)
