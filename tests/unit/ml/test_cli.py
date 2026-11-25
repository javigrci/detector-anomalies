"""FR-004-28, 31: CLI de operación (`train`, `status`, `list`, `activate`)."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from security_anomaly.ml import __main__ as cli
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.service import TrainingResult
from security_anomaly.schemas.ml import EvaluationReport, ModelVersion, RunStatus, TrainingRun

NOW = datetime(2026, 3, 1, tzinfo=UTC)
RUN = uuid.UUID(int=7)
Calls = dict[str, list[dict[str, object]]]
URL = "postgresql+psycopg://anomaly_app:SENTINEL-PASSWORD-x@db:5432/anomaly"


def _version(active: bool = False) -> ModelVersion:
    return ModelVersion(
        version="v0001",
        number=1,
        run_id=RUN,
        created_at=NOW,
        schema_version=1,
        schema_fingerprint="a" * 64,
        params={},
        metrics={},
        dataset_hash="b" * 64,
        artifact_file="model-v0001.joblib",
        artifact_sha256="c" * 64,
        library_versions={},
        active=active,
        activated_at=NOW if active else None,
    )


def _run(status: RunStatus = "succeeded") -> TrainingRun:
    return TrainingRun(
        id=RUN,
        status=status,
        started_at=NOW,
        heartbeat_at=NOW,
        finished_at=NOW,
        params={},
        dataset_hash="b" * 64,
        n_train=7,
        n_calibration=2,
        n_test=2,
        version="v0001",
        error_code=None,
    )


def _report() -> EvaluationReport:
    return EvaluationReport(
        n_test=2,
        score_mean=0.5,
        score_quantiles={"p0": 0.0},
        alert_rate=0.25,
        temporal_stability=(),
        max_alert_rate_gap=0.0,
        incomplete_context={"train": 0, "calibration": 0, "test": 0},
        labelled=False,
        classification=None,
        limitations=("x",),
    )


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {"DATABASE_URL": URL, "MODEL_DIR": str(tmp_path)}


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    seen: dict[str, list[dict[str, object]]] = {"train": [], "activate": []}

    def fake_train(engine: object, settings: object, start: object, end: object, **kw: object):  # type: ignore[no-untyped-def]
        seen["train"].append({"start": start, "end": end, **kw})
        return TrainingResult(run_id=RUN, version=_version(), report=_report())

    def fake_activate(engine: object, settings: object, version: str, *, approved: bool):  # type: ignore[no-untyped-def]
        seen["activate"].append({"version": version, "approved": approved})
        return _version(active=True)

    monkeypatch.setattr(cli, "run_training", fake_train)
    monkeypatch.setattr(cli, "activate_version", fake_activate)
    monkeypatch.setattr(cli, "get_training_run", lambda engine, run_id: _run())
    monkeypatch.setattr(cli, "list_training_runs", lambda engine, limit=10: [_run("running")])
    monkeypatch.setattr(cli, "list_versions", lambda engine: [_version(), _version(True)])
    return seen


def _run_cli(
    argv: list[str], env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    factory = MagicMock(name="engine_factory")
    code = cli.main(argv, env, engine_factory=factory)
    out = capsys.readouterr()
    return code, out.out, out.err


TRAIN = ["train", "--start", "2026-01-01T00:00:00+00:00", "--end", "2026-02-01T00:00:00+00:00"]


def test_train_prints_one_json_line_and_defaults_history_start(
    env: dict[str, str], calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run_cli(TRAIN, env, capsys)
    assert code == 0 and err == ""
    (line,) = out.strip().splitlines()
    data = json.loads(line)
    assert data["version"] == "v0001" and data["run_id"] == str(RUN)
    sent = calls["train"][0]
    assert sent["history_start"] == sent["start"] == datetime(2026, 1, 1, tzinfo=UTC)


def test_the_number_of_trees_overrides_the_environment(
    env: dict[str, str], calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_cli([*TRAIN, "--n-estimators", "25"], env, capsys)
    assert calls["train"][0]["policy"].n_estimators == 25  # type: ignore[attr-defined]
    code, _, _ = _run_cli([*TRAIN, "--n-estimators", "0"], env, capsys)
    assert code == 2


def test_labels_are_read_as_bounded_json_data(
    env: dict[str, str], calls: Calls, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = tmp_path / "labels.json"
    good.write_text(json.dumps({"e1": "normal", "e2": "failure_burst"}))
    code, _, _ = _run_cli([*TRAIN, "--labels", str(good)], env, capsys)
    assert code == 0 and calls["train"][0]["labels"] == {"e1": "normal", "e2": "failure_burst"}
    calls["train"].clear()
    for content in ("no es json SENTINEL-LABELS", '["a"]', '{"e1": 5}', "x" * 6_000_000):
        bad = tmp_path / "bad.json"
        bad.write_text(content)
        code, out, err = _run_cli([*TRAIN, "--labels", str(bad)], env, capsys)
        assert code == 2 and out == "" and "SENTINEL" not in err
    assert calls["train"] == []


def test_invalid_arguments_exit_2_without_echoing_them(
    env: dict[str, str], calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    for argv in (
        ["train", "--start", "SENTINEL-DATE", "--end", "2026-02-01T00:00:00+00:00"],
        ["train", "--start", "2026-01-01T00:00:00", "--end", "2026-02-01T00:00:00+00:00"],
        ["train", "--start", "2026-02-01T00:00:00+00:00", "--end", "2026-01-01T00:00:00+00:00"],
        ["status", "--run", "SENTINEL-RUN"],
        ["drop-everything"],
    ):
        code, out, err = _run_cli(argv, env, capsys)
        assert code == 2 and out == "" and "SENTINEL" not in err and "drop-everything" not in err
    assert calls["train"] == []


def test_missing_configuration_names_the_variable_not_the_value(
    tmp_path: Path, calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _run_cli(TRAIN, {"DATABASE_URL": URL}, capsys)
    assert code == 2 and "MODEL_DIR" in err
    code, _, err = _run_cli(TRAIN, {"MODEL_DIR": str(tmp_path)}, capsys)
    assert code == 2 and "DATABASE_URL" in err
    code, _, err = _run_cli(
        TRAIN,
        {"DATABASE_URL": "mysql://u:SENTINEL-PASSWORD-x@h/d", "MODEL_DIR": str(tmp_path)},
        capsys,
    )
    assert code == 2 and "SENTINEL" not in err


def test_status_and_list_do_not_need_the_model_directory(
    calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run_cli(["status"], {"DATABASE_URL": URL}, capsys)
    assert code == 0 and json.loads(out)["runs"][0]["status"] == "running"
    code, out, _ = _run_cli(["status", "--run", str(RUN)], {"DATABASE_URL": URL}, capsys)
    assert code == 0 and json.loads(out)["status"] == "succeeded"
    code, out, _ = _run_cli(["list"], {"DATABASE_URL": URL}, capsys)
    versions = json.loads(out)["versions"]
    assert [v["active"] for v in versions] == [False, True]


def test_activate_requires_the_explicit_approval_flag_and_never_reaches_the_library(
    env: dict[str, str], calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run_cli(["activate", "v0001"], env, capsys)
    assert code == 1 and out == ""
    assert json.loads(err.strip().splitlines()[-1]) == {"error": "approval_required"}
    assert calls["activate"] == []
    code, out, _ = _run_cli(["activate", "v0001", "--approve"], env, capsys)
    assert code == 0 and json.loads(out)["active"] is True
    assert calls["activate"] == [{"version": "v0001", "approved": True}]


def test_controlled_errors_exit_1_with_only_the_code(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise MlError("training_in_progress")

    monkeypatch.setattr(cli, "run_training", boom)
    code, out, err = _run_cli(TRAIN, env, capsys)
    assert code == 1 and out == ""
    assert json.loads(err.strip().splitlines()[-1]) == {"error": "training_in_progress"}


def test_nothing_secret_is_ever_printed(
    env: dict[str, str], calls: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    for argv in (TRAIN, ["status"], ["list"], ["activate", "v0001", "--approve"]):
        _, out, err = _run_cli(argv, env, capsys)
        assert "SENTINEL" not in out + err and env["MODEL_DIR"] not in out + err
