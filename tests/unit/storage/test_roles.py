"""FR-002-22, 24: nombres de rol y sentencias de aprovisionamiento."""

import logging
from unittest.mock import MagicMock

import pytest
from psycopg import sql
from pydantic import SecretStr

from security_anomaly.storage import roles
from security_anomaly.storage.roles import (
    APP_ROLE,
    MAINT_ROLE,
    MIGRATOR_ROLE,
    RolePasswords,
    build_role_statements,
)


def test_role_names_are_fixed() -> None:
    assert (MIGRATOR_ROLE, APP_ROLE, MAINT_ROLE) == (
        "anomaly_migrator",
        "anomaly_app",
        "anomaly_maint",
    )


def _passwords(**kw: str) -> RolePasswords:
    base = {"migrator": "m" * 12, "app": "a" * 12, "maint": "t" * 12}
    base.update(kw)
    return RolePasswords(
        migrator=SecretStr(base["migrator"]),
        app=SecretStr(base["app"]),
        maint=SecretStr(base["maint"]),
    )


def test_password_is_a_safe_literal() -> None:
    evil = "x'; DROP ROLE postgres; --"
    stmts = build_role_statements(_passwords(app=evil), "anomaly")
    # sql.Literal duplica la comilla simple, así que no cierra la cadena.
    text = "\n".join(_render(s) for s in stmts)
    assert "'x''; DROP ROLE postgres; --'" in text
    assert "x'; DROP" not in text


def _render(statement: sql.Composable) -> str:
    return statement.as_string()


def test_statements_cover_all_three_roles_and_grants() -> None:
    text = "\n".join(_render(s) for s in build_role_statements(_passwords(), "anomaly"))
    for role in (MIGRATOR_ROLE, APP_ROLE, MAINT_ROLE):
        assert role in text
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in text
    assert "GRANT CONNECT ON DATABASE" in text
    assert "GRANT CREATE, USAGE ON SCHEMA public TO anomaly_migrator" in text
    assert "GRANT USAGE ON SCHEMA public TO anomaly_app" in text
    assert "GRANT USAGE ON SCHEMA public TO anomaly_maint" in text


def test_no_table_privileges_are_granted_here() -> None:
    text = "\n".join(_render(s) for s in build_role_statements(_passwords(), "anomaly"))
    assert "ON events" not in text and "ON TABLE" not in text


def test_passwords_never_logged(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(roles, "_database_and_roles", lambda _engine: ("anomaly", frozenset()))
    engine = MagicMock()
    with caplog.at_level(logging.DEBUG):
        roles.provision_roles(engine, _passwords(app="SENTINEL-PASSWORD-x"))
    assert "SENTINEL-PASSWORD-x" not in caplog.text
