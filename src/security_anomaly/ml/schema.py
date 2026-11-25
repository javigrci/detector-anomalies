"""Tablas ``training_runs`` y ``model_versions`` (data-model.md); las crea la migración 0002."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from security_anomaly.storage.schema import metadata

training_runs = Table(
    "training_runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("status", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("params", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("dataset_hash", Text, nullable=True),
    Column("n_train", Integer, nullable=True),
    Column("n_calibration", Integer, nullable=True),
    Column("n_test", Integer, nullable=True),
    Column("version", Text, nullable=True),
    Column("error_code", Text, nullable=True),
)

model_versions = Table(
    "model_versions",
    metadata,
    Column("version", Text, primary_key=True),
    Column("number", Integer, nullable=False, unique=True),
    Column("run_id", Uuid, ForeignKey("training_runs.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("schema_version", Integer, nullable=False),
    Column("schema_fingerprint", Text, nullable=False),
    Column("params", JSONB, nullable=False),
    Column("metrics", JSONB, nullable=False),
    Column("dataset_hash", Text, nullable=False),
    Column("artifact_file", Text, nullable=False),
    Column("artifact_sha256", Text, nullable=False),
    Column("library_versions", JSONB, nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("false")),
    Column("activated_at", DateTime(timezone=True), nullable=True),
)
