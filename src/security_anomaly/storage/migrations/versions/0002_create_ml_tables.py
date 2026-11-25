"""Crea `training_runs` y `model_versions` (incremento 4).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24

Escrita a mano. Concede al rol `anomaly_app` `SELECT` e `INSERT` y `UPDATE` **solo por columna**:
las versiones de modelo son inmutables salvo `active` y `activated_at`, y los entrenamientos solo
cambian de estado, latido y resultado. Dos índices únicos parciales garantizan a lo sumo un
entrenamiento `running` y una versión `active`. Revertir es destructivo: se niega si hay filas salvo
con `-x destructive=yes` (Principio VII).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "anomaly_app"
HEX64 = "^[0-9a-f]{64}$"
RUN_COLUMNS = (
    "status, heartbeat_at, finished_at, dataset_hash, n_train, n_calibration, n_test, "
    "version, error_code"
)


def upgrade() -> None:
    connection = op.get_bind()
    present = connection.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}
    ).first()
    if present is None:
        raise RuntimeError(
            f"Falta el rol de base de datos {APP_ROLE}. Ejecuta antes "
            "`python -m security_anomaly.storage provision-roles` "
            "(o `docker compose --profile setup run --rm db-setup`)."
        )

    op.create_table(
        "training_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("params", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dataset_hash", sa.Text(), nullable=True),
        sa.Column("n_train", sa.Integer(), nullable=True),
        sa.Column("n_calibration", sa.Integer(), nullable=True),
        sa.Column("n_test", sa.Integer(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="training_runs_pkey"),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="ck_training_runs_status"
        ),
        sa.CheckConstraint(
            f"dataset_hash IS NULL OR dataset_hash ~ '{HEX64}'",
            name="ck_training_runs_dataset_hash",
        ),
    )
    op.create_index(
        "uq_training_runs_one_running",
        "training_runs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "model_versions",
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("schema_fingerprint", sa.Text(), nullable=False),
        sa.Column("params", JSONB(), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False),
        sa.Column("dataset_hash", sa.Text(), nullable=False),
        sa.Column("artifact_file", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.Text(), nullable=False),
        sa.Column("library_versions", JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("version", name="model_versions_pkey"),
        sa.UniqueConstraint("number", name="uq_model_versions_number"),
        sa.ForeignKeyConstraint(["run_id"], ["training_runs.id"], name="fk_model_versions_run"),
        sa.CheckConstraint("version ~ '^v[0-9]{4,}$'", name="ck_model_versions_version"),
        sa.CheckConstraint(
            "artifact_file ~ '^model-v[0-9]{4,}\\.joblib$'", name="ck_model_versions_artifact_file"
        ),
        sa.CheckConstraint(
            f"artifact_sha256 ~ '{HEX64}'", name="ck_model_versions_artifact_sha256"
        ),
        sa.CheckConstraint(f"dataset_hash ~ '{HEX64}'", name="ck_model_versions_dataset_hash"),
        sa.CheckConstraint(
            f"schema_fingerprint ~ '{HEX64}'", name="ck_model_versions_schema_fingerprint"
        ),
    )
    op.create_index(
        "uq_model_versions_one_active",
        "model_versions",
        ["active"],
        unique=True,
        postgresql_where=sa.text("active"),
    )

    op.execute(f"GRANT SELECT, INSERT ON training_runs, model_versions TO {APP_ROLE}")
    op.execute(f"GRANT UPDATE ({RUN_COLUMNS}) ON training_runs TO {APP_ROLE}")
    op.execute(f"GRANT UPDATE (active, activated_at) ON model_versions TO {APP_ROLE}")


def downgrade() -> None:
    connection = op.get_bind()
    has_rows = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM model_versions) OR EXISTS (SELECT 1 FROM training_runs)"
        )
    ).scalar_one()
    destructive = context.get_x_argument(as_dictionary=True).get("destructive") == "yes"
    if has_rows and not destructive:
        raise RuntimeError(
            "Las tablas de modelos tienen datos: revertir es destructivo y requiere autorización "
            "explícita. Repite con `alembic -x destructive=yes downgrade ...` si la tienes."
        )
    op.drop_table("model_versions")
    op.drop_table("training_runs")
