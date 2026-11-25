"""FR-004-27, 28: la CLI como proceso aparte: entrenar, listar, activar y consultar el estado."""

import json
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from tests.integration.ml.conftest import LoadedData

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def _env(app_engine: Engine, model_dir: Path) -> dict[str, str]:
    return {
        "DATABASE_URL": app_engine.url.render_as_string(hide_password=False),
        "MODEL_DIR": str(model_dir),
        "PATH": "/usr/bin:/bin",
    }


def _cli(env: Mapping[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "security_anomaly.ml", *args],
        cwd=ROOT,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _train_args(data: LoadedData) -> list[str]:
    return [
        "train",
        "--start",
        data.start.isoformat(),
        "--end",
        data.end.isoformat(),
        "--history-start",
        data.history_start.isoformat(),
    ]


def _one_json_line(text_: str) -> dict[str, object]:
    lines = text_.strip().splitlines()
    assert len(lines) == 1, text_
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def test_train_list_activate_and_status_as_separate_processes(
    app_engine: Engine, loaded: LoadedData, tmp_path: Path
) -> None:
    env = _env(app_engine, tmp_path)
    trained = _cli(env, *_train_args(loaded))
    assert trained.returncode == 0, trained.stderr
    info = _one_json_line(trained.stdout)
    assert info["version"] == "v0001"
    assert (tmp_path / "model-v0001.joblib").is_file()

    versions = json.loads(_cli(env, "list").stdout)["versions"]
    assert [v["version"] for v in versions] == ["v0001"]
    assert versions[0]["active"] is False

    refused = _cli(env, "activate", "v0001")
    assert refused.returncode == 1 and json.loads(refused.stderr.strip()) == {
        "error": "approval_required"
    }
    activated = _cli(env, "activate", "v0001", "--approve")
    assert activated.returncode == 0, activated.stderr
    assert _one_json_line(activated.stdout)["active"] is True

    status = _one_json_line(_cli(env, "status", "--run", str(info["run_id"])).stdout)
    assert (status["status"], status["version"]) == ("succeeded", "v0001")


def test_a_second_training_is_rejected_while_one_is_running(
    app_engine: Engine, migrator_engine: Engine, loaded: LoadedData, tmp_path: Path
) -> None:
    env = _env(app_engine, tmp_path)
    with migrator_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO training_runs (id, status, params) "
                "VALUES (gen_random_uuid(), 'running', '{}')"
            )
        )
    rejected = _cli(env, *_train_args(loaded))
    assert rejected.returncode == 1 and rejected.stdout == ""
    assert json.loads(rejected.stderr.strip()) == {"error": "training_in_progress"}
    assert list(tmp_path.iterdir()) == []
    with migrator_engine.begin() as connection:
        connection.execute(text("UPDATE training_runs SET status = 'failed'"))
    assert _cli(env, *_train_args(loaded)).returncode == 0


def test_the_database_is_not_blocked_while_a_training_runs(
    app_engine: Engine, loaded: LoadedData, tmp_path: Path
) -> None:
    env = _env(app_engine, tmp_path)
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "security_anomaly.ml", *_train_args(loaded)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        running = 0
        while time.monotonic() < deadline and process.poll() is None and not running:
            with app_engine.connect() as connection:
                running = int(
                    connection.execute(
                        text("SELECT count(*) FROM training_runs WHERE status = 'running'")
                    ).scalar_one()
                )
            time.sleep(0.05)
        started = time.perf_counter()
        with app_engine.connect() as connection:
            connection.execute(text("SELECT count(*) FROM events")).scalar_one()
        assert time.perf_counter() - started < 2.0  # el servicio sigue respondiendo
        stdout, stderr = process.communicate(timeout=300)
    finally:
        if process.poll() is None:
            process.kill()
    assert process.returncode == 0, stderr
    assert _one_json_line(stdout)["version"] == "v0001"
