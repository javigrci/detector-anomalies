"""Fixtures de integración: base de datos efímera, roles aleatorios y migración (research R13).

`DATABASE_URL` es aquí la conexión de administrador de PostgreSQL (contracts/environment.md); las
contraseñas de los roles se generan al vuelo y solo viven en el proceso de test.
"""

import contextlib
import os
import secrets
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from security_anomaly.storage.roles import (
    ALL_ROLES,
    APP_ROLE,
    MAINT_ROLE,
    MIGRATOR_ROLE,
    RolePasswords,
    provision_roles,
)

ROOT = Path(__file__).resolve().parents[2]


def _admin_url() -> URL:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.fail("Los tests de integración requieren DATABASE_URL", pytrace=False)
    return make_url(value)


def _create_database(admin: URL, name: str) -> None:
    engine = create_engine(admin.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()


def _drop_database(admin: URL, name: str) -> None:
    engine = create_engine(admin.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    engine.dispose()


@pytest.fixture(scope="session")
def admin_url() -> URL:
    return _admin_url()


@pytest.fixture(scope="session")
def role_passwords() -> dict[str, str]:
    return {
        MIGRATOR_ROLE: secrets.token_hex(12),
        APP_ROLE: secrets.token_hex(12),
        MAINT_ROLE: secrets.token_hex(12),
    }


@pytest.fixture(scope="session")
def db_name(admin_url: URL) -> Iterator[str]:
    name = f"anomaly_test_{secrets.token_hex(6)}"
    _create_database(admin_url, name)
    yield name
    _drop_database(admin_url, name)


@pytest.fixture(scope="session")
def role_url(admin_url: URL, role_passwords: dict[str, str]) -> Callable[[str, str], str]:
    def build(role: str, database: str) -> str:
        url = admin_url.set(database=database, username=role, password=role_passwords[role])
        return url.render_as_string(hide_password=False)

    return build


@pytest.fixture(scope="session")
def provisioned_roles(
    admin_url: URL, db_name: str, role_passwords: dict[str, str]
) -> Iterator[None]:
    engine = create_engine(admin_url.set(database=db_name))
    provision_roles(
        engine,
        RolePasswords(
            migrator=SecretStr(role_passwords[MIGRATOR_ROLE]),
            app=SecretStr(role_passwords[APP_ROLE]),
            maint=SecretStr(role_passwords[MAINT_ROLE]),
        ),
    )
    engine.dispose()
    yield
    # Los roles son globales del clúster: se eliminan al terminar (ya sin la base de datos).
    cleanup = create_engine(admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with cleanup.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        for role in ALL_ROLES:
            # Si otro paso (p. ej. la CI) ya concedió permisos en otra base de datos, se conserva.
            with contextlib.suppress(DBAPIError):
                connection.execute(text(f"DROP ROLE IF EXISTS {role}"))
    cleanup.dispose()


def run_alembic(
    migration_url: str, *args: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Ejecuta Alembic en un proceso aparte con solo `MIGRATION_DATABASE_URL` (rol migrador)."""
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL"}}
    env["MIGRATION_DATABASE_URL"] = migration_url
    env.update(extra_env or {})
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(scope="session")
def migrated(provisioned_roles: None, db_name: str, role_url: Callable[[str, str], str]) -> str:
    """Nombre de la base de datos ya migrada (rol migrador)."""
    result = run_alembic(role_url(MIGRATOR_ROLE, db_name), "upgrade", "head")
    assert result.returncode == 0, result.stderr
    return db_name


@pytest.fixture(scope="session")
def admin_engine(admin_url: URL, db_name: str) -> Iterator[Engine]:
    engine = create_engine(admin_url.set(database=db_name))
    yield engine
    engine.dispose()


def _role_engine(role: str, database: str, role_url: Callable[[str, str], str]) -> Iterator[Engine]:
    engine = create_engine(role_url(role, database), pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrator_engine(migrated: str, role_url: Callable[[str, str], str]) -> Iterator[Engine]:
    yield from _role_engine(MIGRATOR_ROLE, migrated, role_url)


@pytest.fixture(scope="session")
def app_engine(migrated: str, role_url: Callable[[str, str], str]) -> Iterator[Engine]:
    yield from _role_engine(APP_ROLE, migrated, role_url)


@pytest.fixture(scope="session")
def maint_engine(migrated: str, role_url: Callable[[str, str], str]) -> Iterator[Engine]:
    yield from _role_engine(MAINT_ROLE, migrated, role_url)


@pytest.fixture
def fresh_database(admin_url: URL, provisioned_roles: None) -> Iterator[Callable[[], str]]:
    """Fábrica de bases de datos vacías con los roles ya concedidos; se eliminan al terminar."""
    created: list[str] = []

    def make() -> str:
        name = f"anomaly_fresh_{secrets.token_hex(6)}"
        _create_database(admin_url, name)
        created.append(name)
        engine = create_engine(admin_url.set(database=name), isolation_level="AUTOCOMMIT")
        with engine.connect() as connection:
            for role in ALL_ROLES:
                connection.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO {role}'))
            connection.execute(text(f"GRANT CREATE, USAGE ON SCHEMA public TO {MIGRATOR_ROLE}"))
            for role in (APP_ROLE, MAINT_ROLE):
                connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        engine.dispose()
        return name

    yield make
    for name in created:
        _drop_database(admin_url, name)
