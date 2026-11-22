"""FR-002-22: el aprovisionamiento es idempotente, rota contraseñas y no filtra secretos."""

import secrets

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from security_anomaly.storage import RolePasswords, StorageError, provision_roles
from security_anomaly.storage.roles import APP_ROLE, MAINT_ROLE, MIGRATOR_ROLE

pytestmark = pytest.mark.integration


def _passwords(raw: dict[str, str]) -> RolePasswords:
    return RolePasswords(
        migrator=SecretStr(raw[MIGRATOR_ROLE]),
        app=SecretStr(raw[APP_ROLE]),
        maint=SecretStr(raw[MAINT_ROLE]),
    )


def _verifier(admin_engine: Engine, role: str) -> str:
    with admin_engine.connect() as connection:
        return str(
            connection.execute(
                text("SELECT rolpassword FROM pg_authid WHERE rolname = :r"), {"r": role}
            ).scalar_one()
        )


def test_provisioning_twice_changes_nothing(
    admin_engine: Engine, role_passwords: dict[str, str], provisioned_roles: None
) -> None:
    provision_roles(admin_engine, _passwords(role_passwords))
    provision_roles(admin_engine, _passwords(role_passwords))
    with admin_engine.connect() as connection:
        names = set(
            connection.execute(
                text("SELECT rolname FROM pg_roles WHERE rolname LIKE 'anomaly\\_%'")
            ).scalars()
        )
    assert {MIGRATOR_ROLE, APP_ROLE, MAINT_ROLE} <= names


def test_the_roles_are_not_privileged(admin_engine: Engine, provisioned_roles: None) -> None:
    with admin_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolcanlogin "
                "FROM pg_roles WHERE rolname IN ('anomaly_migrator','anomaly_app','anomaly_maint')"
            )
        ).all()
    assert len(rows) == 3
    for _name, superuser, createdb, createrole, replication, can_login in rows:
        assert (superuser, createdb, createrole, replication, can_login) == (
            False,
            False,
            False,
            False,
            True,
        )


def test_a_new_password_replaces_the_old_one(
    admin_engine: Engine, role_passwords: dict[str, str], provisioned_roles: None
) -> None:
    """Con la autenticación `trust` de la CI no se puede probar el inicio de sesión: se comprueba
    que el verificador SCRAM del rol cambia al reaprovisionar con otra contraseña."""
    before = _verifier(admin_engine, MAINT_ROLE)
    assert before.startswith("SCRAM-SHA-256$")
    try:
        provision_roles(
            admin_engine, _passwords({**role_passwords, MAINT_ROLE: secrets.token_hex(12)})
        )
        changed = _verifier(admin_engine, MAINT_ROLE)
    finally:
        provision_roles(admin_engine, _passwords(role_passwords))
    assert changed != before
    assert changed.startswith("SCRAM-SHA-256$")


def test_public_has_no_create_on_the_schema(admin_engine: Engine, provisioned_roles: None) -> None:
    with admin_engine.connect() as connection:
        acl = connection.execute(
            text("SELECT nspacl::text FROM pg_namespace WHERE nspname = 'public'")
        ).scalar_one()
    public_entries = [e for e in acl.strip("{}").split(",") if e.startswith("=")]
    assert all("C" not in e.split("/")[0] for e in public_entries), acl


def test_errors_do_not_contain_passwords(admin_url: URL) -> None:
    dead = create_engine(
        admin_url.set(port=1, password="SENTINEL-PASSWORD-admin"),
        connect_args={"connect_timeout": 1},
    )
    secrets_ = {
        MIGRATOR_ROLE: "SENTINEL-PASSWORD-m1",
        APP_ROLE: "SENTINEL-PASSWORD-a2",
        MAINT_ROLE: "SENTINEL-PASSWORD-t3",
    }
    try:
        with pytest.raises(StorageError) as exc:
            provision_roles(dead, _passwords(secrets_))
    finally:
        dead.dispose()
    assert exc.value.code == "unavailable"
    assert "SENTINEL" not in f"{exc.value!s} {exc.value!r}"
    assert exc.value.__cause__ is None


def test_a_permission_failure_is_controlled(
    app_engine: Engine, role_passwords: dict[str, str]
) -> None:
    """Quien no es administrador no puede aprovisionar: error controlado y sin secretos."""
    with pytest.raises(StorageError) as exc:
        provision_roles(app_engine, _passwords(role_passwords))
    assert exc.value.code == "permission_denied"
    assert role_passwords[APP_ROLE] not in f"{exc.value!s} {exc.value!r}"
