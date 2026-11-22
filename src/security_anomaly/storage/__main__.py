"""CLI mínima de operación: ``provision-roles`` y ``purge`` (research R10; contracts/operations.md).

Solo ``argparse``. Una línea JSON en la salida estándar con recuentos; nunca valores de eventos ni
credenciales. Códigos de salida: 0 correcto, 2 configuración o argumentos inválidos (se nombra la
variable, no su valor), 1 error de base de datos (solo el ``code``).
"""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import NoReturn

from pydantic import SecretStr
from sqlalchemy import Engine, create_engine

from security_anomaly.core.config import ConfigError
from security_anomaly.storage.config import (
    load_admin_settings,
    load_maintenance_settings,
    load_storage_policy,
)
from security_anomaly.storage.errors import StorageError
from security_anomaly.storage.retention import purge_events
from security_anomaly.storage.roles import ALL_ROLES, RolePasswords, provision_roles

EngineFactory = Callable[[str], Engine]
_CONNECT_TIMEOUT_S = 5


def _default_engine(url: str) -> Engine:
    return create_engine(
        url, pool_pre_ping=True, connect_args={"connect_timeout": _CONNECT_TIMEOUT_S}
    )


class _Parser(argparse.ArgumentParser):
    """Los errores de uso no repiten lo que escribió el usuario (podría ser un secreto)."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, "Argumentos inválidos.\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m security_anomaly.storage")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("provision-roles", help="crea o actualiza los tres roles de BD")
    purge = commands.add_parser(
        "purge", help="borra los eventos anteriores al periodo de retención"
    )
    purge.add_argument("--days", type=int, default=None, help="sustituye a RETENTION_DAYS (≥ 1)")
    purge.add_argument("--dry-run", action="store_true", help="informa sin borrar")
    return parser


def _fail(code: int, message: str) -> int:
    print(message, file=sys.stderr)
    return code


def _run_purge(
    args: argparse.Namespace, environ: Mapping[str, str] | None, engine_factory: EngineFactory
) -> int:
    if args.days is not None and args.days < 1:
        return _fail(2, "--days debe ser al menos 1")
    settings = load_maintenance_settings(environ)
    policy = load_storage_policy(environ)
    engine = engine_factory(settings.maintenance_database_url.get_secret_value())
    try:
        result = purge_events(
            engine,
            retention_days=policy.retention_days if args.days is None else args.days,
            dry_run=args.dry_run,
            policy=policy,
        )
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "retention_days": result.retention_days,
                "cutoff": result.cutoff.isoformat(),
                "dry_run": result.dry_run,
                "affected": result.affected,
            }
        )
    )
    return 0


def _run_provision(environ: Mapping[str, str] | None, engine_factory: EngineFactory) -> int:
    settings = load_admin_settings(environ)
    engine = engine_factory(settings.admin_database_url.get_secret_value())
    try:
        provision_roles(
            engine,
            RolePasswords(
                migrator=SecretStr(settings.migrator_db_password.get_secret_value()),
                app=SecretStr(settings.app_db_password.get_secret_value()),
                maint=SecretStr(settings.maint_db_password.get_secret_value()),
            ),
        )
    finally:
        engine.dispose()
    print(json.dumps({"command": "provision-roles", "roles": len(ALL_ROLES)}))
    return 0


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    engine_factory: EngineFactory = _default_engine,
) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exit_:
        return int(exit_.code) if isinstance(exit_.code, int) else 2
    try:
        if args.command == "purge":
            return _run_purge(args, environ, engine_factory)
        return _run_provision(environ, engine_factory)
    except ConfigError as exc:
        return _fail(2, str(exc))
    except StorageError as exc:
        return _fail(1, json.dumps({"error": exc.code}))
    except Exception:
        return _fail(1, json.dumps({"error": "unknown"}))


if __name__ == "__main__":
    sys.exit(main())
