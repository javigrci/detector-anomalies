"""Tabla ``events`` (data-model.md). El esquema real solo lo crea la migración de Alembic."""

from sqlalchemy import Column, DateTime, Index, MetaData, Table, Text, Uuid, func
from sqlalchemy.dialects.postgresql import INET

metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("source", Text, primary_key=True),
    Column("event_id", Text, primary_key=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("event_type", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("user_pseudonym", Text, nullable=True),
    Column("source_ip", INET, nullable=True),
    Column("host", Text, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("batch_id", Uuid, nullable=False),
)

Index("ix_events_timestamp", events.c.timestamp, events.c.source, events.c.event_id)
Index("ix_events_source_timestamp", events.c.source, events.c.timestamp)
Index(
    "ix_events_ip_timestamp",
    events.c.source_ip,
    events.c.timestamp,
    postgresql_where=events.c.source_ip.is_not(None),
)
Index(
    "ix_events_user_timestamp",
    events.c.user_pseudonym,
    events.c.timestamp,
    postgresql_where=events.c.user_pseudonym.is_not(None),
)
Index("ix_events_ingested_at", events.c.ingested_at)
