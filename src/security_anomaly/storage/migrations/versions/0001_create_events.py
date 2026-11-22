"""Crea la tabla `events` (incremento 2).

Revision ID: 0001
Revises:
Create Date: 2026-11-22

Escrita a mano (sin autogeneración). Concede los permisos mínimos a `anomaly_app` (insertar y
consultar) y `anomaly_maint` (consultar y borrar); si faltan los roles, falla pidiendo
aprovisionarlos.
Las CHECK son una fotografía del catálogo v1 del incremento 1; un test las compara con los enums.
Revertir es destructivo: se niega si hay filas salvo con `-x destructive=yes` (Principio VII).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects.postgresql import INET

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT_TYPES = ("authentication", "privilege_escalation", "other")
ACTIONS = ("login", "invalid_user", "sudo", "other")
OUTCOMES = ("success", "failure", "unknown")
SOURCE_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
PSEUDONYM_PATTERN = r"^usr_[0-9a-f]{32}$"

APP_ROLE = "anomaly_app"
MAINT_ROLE = "anomaly_maint"


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def missing_roles(connection: sa.Connection, roles: Sequence[str]) -> list[str]:
    """Roles de la lista que no existen en el servidor (en el orden dado)."""
    present = set(
        connection.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:names)"),
            {"names": list(roles)},
        ).scalars()
    )
    return [role for role in roles if role not in present]


def missing_roles_message(missing: Sequence[str]) -> str:
    return (
        "Faltan roles de base de datos: "
        + ", ".join(missing)
        + ". Ejecuta antes `python -m security_anomaly.storage provision-roles` "
        "(o `docker compose --profile setup run --rm db-setup`)."
    )


def upgrade() -> None:
    connection = op.get_bind()
    missing = missing_roles(connection, [APP_ROLE, MAINT_ROLE])
    if missing:
        raise RuntimeError(missing_roles_message(missing))

    op.create_table(
        "events",
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("user_pseudonym", sa.Text(), nullable=True),
        sa.Column("source_ip", INET(), nullable=True),
        sa.Column("host", sa.Text(), nullable=True),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("source", "event_id", name="events_pkey"),
        sa.CheckConstraint(f"source ~ '{SOURCE_PATTERN}'", name="ck_events_source"),
        sa.CheckConstraint("char_length(event_id) BETWEEN 1 AND 256", name="ck_events_event_id"),
        sa.CheckConstraint(_in_list("event_type", EVENT_TYPES), name="ck_events_event_type"),
        sa.CheckConstraint(_in_list("action", ACTIONS), name="ck_events_action"),
        sa.CheckConstraint(_in_list("outcome", OUTCOMES), name="ck_events_outcome"),
        sa.CheckConstraint(
            f"user_pseudonym IS NULL OR user_pseudonym ~ '{PSEUDONYM_PATTERN}'",
            name="ck_events_user_pseudonym",
        ),
        sa.CheckConstraint("host IS NULL OR char_length(host) <= 256", name="ck_events_host"),
    )
    op.create_index("ix_events_timestamp", "events", ["timestamp", "source", "event_id"])
    op.create_index("ix_events_source_timestamp", "events", ["source", "timestamp"])
    op.create_index(
        "ix_events_ip_timestamp",
        "events",
        ["source_ip", "timestamp"],
        postgresql_where=sa.text("source_ip IS NOT NULL"),
    )
    op.create_index(
        "ix_events_user_timestamp",
        "events",
        ["user_pseudonym", "timestamp"],
        postgresql_where=sa.text("user_pseudonym IS NOT NULL"),
    )
    op.create_index("ix_events_ingested_at", "events", ["ingested_at"])

    op.execute(f"GRANT SELECT, INSERT ON events TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, DELETE ON events TO {MAINT_ROLE}")


def downgrade() -> None:
    connection = op.get_bind()
    has_rows = connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM events)")).scalar_one()
    destructive = context.get_x_argument(as_dictionary=True).get("destructive") == "yes"
    if has_rows and not destructive:
        raise RuntimeError(
            "La tabla `events` tiene datos: revertir es destructivo y requiere autorización "
            "explícita. Repite con `alembic -x destructive=yes downgrade ...` si la tienes."
        )
    op.drop_table("events")
