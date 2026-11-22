"""FR-002-20, 26: CLI de operación (`provision-roles` y `purge`)."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from security_anomaly.schemas.storage import PurgeResult
from security_anomaly.storage import __main__ as cli
from security_anomaly.storage.errors import StorageError

SENTINEL_URL = "postgresql+psycopg://anomaly_maint:SENTINEL-PASSWORD-x@db:5432/anomaly"
ENV = {"MAINTENANCE_DATABASE_URL": SENTINEL_URL}
ADMIN_ENV = {
    "ADMIN_DATABASE_URL": "postgresql+psycopg://postgres:SENTINEL-PASSWORD-a@db:5432/anomaly",
    "MIGRATOR_DB_PASSWORD": "SENTINEL-PASSWORD-m1",
    "APP_DB_PASSWORD": "SENTINEL-PASSWORD-a2",
    "MAINT_DB_PASSWORD": "SENTINEL-PASSWORD-t3",
}


@pytest.fixture
def purge_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_purge(engine: object, **kwargs: object) -> PurgeResult:
        calls.append(kwargs)
        days = kwargs["retention_days"]
        assert isinstance(days, int)
        return PurgeResult(
            retention_days=days,
            cutoff=datetime(2026, 3, 1, tzinfo=UTC),
            dry_run=bool(kwargs["dry_run"]),
            affected=7,
        )

    monkeypatch.setattr(cli, "purge_events", fake_purge)
    return calls


def _run(
    argv: list[str], env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    code = cli.main(argv, env, engine_factory=lambda _url: MagicMock())
    out = capsys.readouterr()
    return code, out.out, out.err


def test_purge_prints_one_json_line(
    capsys: pytest.CaptureFixture[str], purge_calls: list[dict[str, object]]
) -> None:
    code, out, err = _run(["purge", "--dry-run"], ENV, capsys)
    assert code == 0 and err == ""
    lines = out.strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "retention_days": 90,
        "cutoff": "2026-03-01T00:00:00+00:00",
        "dry_run": True,
        "affected": 7,
    }
    assert purge_calls[0]["dry_run"] is True


def test_retention_comes_from_the_environment_and_days_overrides_it(
    capsys: pytest.CaptureFixture[str], purge_calls: list[dict[str, object]]
) -> None:
    _run(["purge"], {**ENV, "RETENTION_DAYS": "30"}, capsys)
    _run(["purge", "--days", "5"], {**ENV, "RETENTION_DAYS": "30"}, capsys)
    assert [c["retention_days"] for c in purge_calls] == [30, 5]
    assert [c["dry_run"] for c in purge_calls] == [False, False]


@pytest.mark.parametrize("days", ["0", "-3", "abc", "1.5"])
def test_invalid_days_exit_2_without_touching_anything(
    days: str, capsys: pytest.CaptureFixture[str], purge_calls: list[dict[str, object]]
) -> None:
    code, out, _ = _run(["purge", "--days", days], ENV, capsys)
    assert code == 2
    assert out == ""
    assert purge_calls == []


def test_missing_maintenance_url_names_the_variable(
    capsys: pytest.CaptureFixture[str], purge_calls: list[dict[str, object]]
) -> None:
    code, out, err = _run(["purge"], {}, capsys)
    assert code == 2 and out == ""
    assert "MAINTENANCE_DATABASE_URL" in err
    assert purge_calls == []


def test_invalid_retention_env_exits_2_and_names_the_variable(
    capsys: pytest.CaptureFixture[str], purge_calls: list[dict[str, object]]
) -> None:
    code, _, err = _run(["purge"], {**ENV, "RETENTION_DAYS": "0"}, capsys)
    assert code == 2
    assert "RETENTION_DAYS" in err
    assert purge_calls == []


def test_a_database_error_exits_1_with_only_the_code(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(engine: object, **kwargs: object) -> PurgeResult:
        raise StorageError("permission_denied")

    monkeypatch.setattr(cli, "purge_events", boom)
    code, out, err = _run(["purge"], ENV, capsys)
    assert code == 1 and out == ""
    assert json.loads(err.strip().splitlines()[-1]) == {"error": "permission_denied"}


def test_nothing_secret_is_ever_printed(
    capsys: pytest.CaptureFixture[str], purge_calls: list[dict[str, object]]
) -> None:
    for argv, env in (
        (["purge"], ENV),
        (["purge", "--days", "SENTINEL-DAYS"], ENV),
        (["purge"], {"MAINTENANCE_DATABASE_URL": "mysql://u:SENTINEL-PASSWORD-x@h/db"}),
    ):
        _, out, err = _run(argv, env, capsys)
        assert "SENTINEL" not in out + err


def test_unknown_subcommand_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(["drop-everything"], ENV, capsys)
    assert code == 2
    assert "drop-everything" not in err


def test_provision_roles_runs_with_the_admin_settings(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_provision(engine: object, passwords: object) -> None:
        seen["called"] = True
        seen["passwords"] = passwords

    monkeypatch.setattr(cli, "provision_roles", fake_provision)
    code, out, err = _run(["provision-roles"], ADMIN_ENV, capsys)
    assert code == 0 and err == ""
    assert json.loads(out.strip()) == {"command": "provision-roles", "roles": 3}
    assert seen["called"] is True
    assert "SENTINEL" not in out


def test_provision_roles_with_missing_passwords_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {k: v for k, v in ADMIN_ENV.items() if k != "APP_DB_PASSWORD"}
    code, _, err = _run(["provision-roles"], env, capsys)
    assert code == 2
    assert "APP_DB_PASSWORD" in err
    assert "SENTINEL" not in err


def test_provision_roles_does_not_need_the_maintenance_url(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "provision_roles", lambda engine, passwords: None)
    code, _, _ = _run(["provision-roles"], ADMIN_ENV, capsys)
    assert code == 0
