"""Roles de la base de datos y aprovisionamiento idempotente (FR-002-22; research R7).

Una sola implementación: la usan los tests, la CI y Compose. Las contraseñas se escriben como
literales seguros con ``psycopg.sql`` (el DDL no admite parámetros) y nunca se registran.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import psycopg
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from security_anomaly.storage.errors import translate_db_error

logger = logging.getLogger(__name__)

MIGRATOR_ROLE = "anomaly_migrator"
APP_ROLE = "anomaly_app"
MAINT_ROLE = "anomaly_maint"
ALL_ROLES = (MIGRATOR_ROLE, APP_ROLE, MAINT_ROLE)


@dataclass(frozen=True, repr=False)
class RolePasswords:
    """Contraseñas de los tres roles; ``repr`` no las muestra."""

    migrator: SecretStr
    app: SecretStr
    maint: SecretStr

    def __repr__(self) -> str:
        return "RolePasswords(***)"


def build_role_statements(
    passwords: RolePasswords, database: str, existing: Iterable[str] = ()
) -> list[sql.Composable]:
    """Sentencias que crean o actualizan los roles y fijan sus privilegios base."""
    present = set(existing)
    statements: list[sql.Composable] = []
    for role, password in (
        (MIGRATOR_ROLE, passwords.migrator),
        (APP_ROLE, passwords.app),
        (MAINT_ROLE, passwords.maint),
    ):
        verb = "ALTER" if role in present else "CREATE"
        statements.append(
            sql.SQL(
                verb + " ROLE " + role + " LOGIN PASSWORD {} "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
            ).format(sql.Literal(password.get_secret_value()))
        )
    statements.append(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    for role in ALL_ROLES:
        statements.append(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO " + role).format(sql.Identifier(database))
        )
    statements.append(sql.SQL("GRANT CREATE, USAGE ON SCHEMA public TO " + MIGRATOR_ROLE))
    statements.append(sql.SQL("GRANT USAGE ON SCHEMA public TO " + APP_ROLE))
    statements.append(sql.SQL("GRANT USAGE ON SCHEMA public TO " + MAINT_ROLE))
    return statements


def _database_and_roles(admin_engine: Engine) -> tuple[str, frozenset[str]]:
    with admin_engine.connect() as connection:
        database = str(connection.execute(text("SELECT current_database()")).scalar_one())
        rows = connection.execute(
            text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:names)"),
            {"names": list(ALL_ROLES)},
        ).scalars()
        return database, frozenset(str(name) for name in rows)


def provision_roles(admin_engine: Engine, passwords: RolePasswords) -> None:
    """Crea o actualiza los tres roles; repetirlo no cambia nada salvo las contraseñas."""
    try:
        database, existing = _database_and_roles(admin_engine)
        with admin_engine.begin() as connection:
            cursor = connection.connection.cursor()
            for statement in build_role_statements(passwords, database, existing):
                cursor.execute(statement)
    except (SQLAlchemyError, psycopg.Error) as exc:
        raise translate_db_error(exc) from None
    logger.info("roles_provisioned", extra={"fields": {"roles": len(ALL_ROLES)}})
