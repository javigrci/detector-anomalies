"""FR-004-27, SC-007: concurrencia 1, estado consultable y entrenamientos huérfanos."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from security_anomaly.ml import registry
from security_anomaly.ml.config import MlSettings
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.service import run_training
from tests.integration.ml.conftest import LoadedData

pytestmark = pytest.mark.integration


def _try_begin(engine: Engine) -> str:
    try:
        registry.begin_training_run(engine, {})
    except MlError as error:
        return error.code
    return "started"


def test_two_simultaneous_runs_start_exactly_one(app_engine: Engine) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: _try_begin(app_engine), range(2)))
    assert sorted(outcomes) == ["started", "training_in_progress"]


def test_eight_simultaneous_runs_start_at_most_one(app_engine: Engine) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda _: _try_begin(app_engine), range(8)))
    assert outcomes.count("started") == 1
    assert set(outcomes) <= {"started", "training_in_progress"}
    with app_engine.connect() as connection:
        running = connection.execute(
            text("SELECT count(*) FROM training_runs WHERE status = 'running'")
        )
        assert running.scalar_one() == 1


def test_a_finished_run_does_not_block_the_next_one(app_engine: Engine) -> None:
    first = registry.begin_training_run(app_engine, {})
    registry.fail_training_run(app_engine, first, "training_failed")
    registry.begin_training_run(app_engine, {})
    states = {r.id: r.status for r in registry.list_training_runs(app_engine)}
    assert states[first] == "failed"


def test_the_state_is_queryable_through_its_phases(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData
) -> None:
    run_id = registry.begin_training_run(app_engine, {"x": 1})
    running = registry.get_training_run(app_engine, run_id)
    assert (running.status, running.finished_at, running.version) == ("running", None, None)
    registry.fail_training_run(app_engine, run_id, "training_failed")
    failed = registry.get_training_run(app_engine, run_id)
    assert (failed.status, failed.error_code) == ("failed", "training_failed")
    assert failed.finished_at is not None
    result = run_training(
        app_engine, settings, loaded.start, loaded.end, history_start=loaded.history_start
    )
    done = registry.get_training_run(app_engine, result.run_id)
    assert (done.status, done.version) == ("succeeded", "v0001")


def test_an_unknown_run_is_a_controlled_error(app_engine: Engine) -> None:
    import uuid

    with pytest.raises(MlError) as caught:
        registry.get_training_run(app_engine, uuid.uuid4())
    assert caught.value.code == "unknown_run"


def _age_heartbeat(migrator_engine: Engine, minutes: int) -> None:
    with migrator_engine.begin() as connection:
        connection.execute(
            text("UPDATE training_runs SET heartbeat_at = now() - make_interval(mins => :m)"),
            {"m": minutes},
        )


def test_a_stale_run_is_marked_failed_and_unblocks_the_next(
    app_engine: Engine, migrator_engine: Engine
) -> None:
    stale = registry.begin_training_run(app_engine, {})
    _age_heartbeat(migrator_engine, 120)
    assert registry.mark_stale_runs_failed(app_engine, timedelta(minutes=60)) == 1
    run = registry.get_training_run(app_engine, stale)
    assert (run.status, run.error_code) == ("failed", "stale")
    assert registry.begin_training_run(app_engine, {}) is not None


def test_a_recent_heartbeat_is_never_marked_and_touching_refreshes_it(
    app_engine: Engine, migrator_engine: Engine
) -> None:
    run_id = registry.begin_training_run(app_engine, {})
    assert registry.mark_stale_runs_failed(app_engine, timedelta(minutes=60)) == 0
    _age_heartbeat(migrator_engine, 30)
    old = registry.get_training_run(app_engine, run_id).heartbeat_at
    registry.touch_training_run(app_engine, run_id)
    assert registry.get_training_run(app_engine, run_id).heartbeat_at > old
    assert registry.mark_stale_runs_failed(app_engine, timedelta(minutes=60)) == 0


def test_training_recovers_a_stale_run_before_starting(
    app_engine: Engine,
    migrator_engine: Engine,
    settings: MlSettings,
    loaded: LoadedData,
) -> None:
    registry.begin_training_run(app_engine, {})
    _age_heartbeat(migrator_engine, 24 * 60)
    result = run_training(
        app_engine, settings, loaded.start, loaded.end, history_start=loaded.history_start
    )
    assert result.version.version == "v0001"
    assert {r.status for r in registry.list_training_runs(app_engine)} == {"failed", "succeeded"}


def test_a_live_run_blocks_a_new_training_without_side_effects(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData, tmp_path: Path
) -> None:
    live = registry.begin_training_run(app_engine, {})
    with pytest.raises(MlError) as caught:
        run_training(
            app_engine, settings, loaded.start, loaded.end, history_start=loaded.history_start
        )
    assert caught.value.code == "training_in_progress"
    assert registry.get_training_run(app_engine, live).status == "running"
    assert len(registry.list_training_runs(app_engine)) == 1
    assert registry.list_versions(app_engine) == [] and list(tmp_path.iterdir()) == []
