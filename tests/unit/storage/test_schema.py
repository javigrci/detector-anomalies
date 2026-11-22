"""FR-002-01, 02, 06, 18: la tabla `events` coincide con data-model.md."""

from sqlalchemy import DateTime, Index, Uuid
from sqlalchemy.dialects.postgresql import INET

from security_anomaly.storage.schema import events, metadata

COLUMNS = {
    "source": False,
    "event_id": False,
    "timestamp": False,
    "event_type": False,
    "action": False,
    "outcome": False,
    "user_pseudonym": True,
    "source_ip": True,
    "host": True,
    "ingested_at": False,
    "batch_id": False,
}


def test_columns_and_nullability() -> None:
    assert {c.name: c.nullable for c in events.columns} == COLUMNS


def test_forbidden_columns_absent() -> None:
    assert not {"username", "out_of_order", "position"} & set(events.c.keys())
    assert not any("key" in name and "version" in name for name in events.c.keys())  # noqa: SIM118


def test_primary_key() -> None:
    assert [c.name for c in events.primary_key.columns] == ["source", "event_id"]


def test_types() -> None:
    assert isinstance(events.c.timestamp.type, DateTime) and events.c.timestamp.type.timezone
    assert isinstance(events.c.ingested_at.type, DateTime) and events.c.ingested_at.type.timezone
    assert isinstance(events.c.source_ip.type, INET)
    assert isinstance(events.c.batch_id.type, Uuid)


def test_indexes() -> None:
    by_name = {str(i.name): i for i in events.indexes if isinstance(i, Index)}
    cols = {n: [c.name for c in i.columns] for n, i in by_name.items()}
    assert cols == {
        "ix_events_timestamp": ["timestamp", "source", "event_id"],
        "ix_events_source_timestamp": ["source", "timestamp"],
        "ix_events_ip_timestamp": ["source_ip", "timestamp"],
        "ix_events_user_timestamp": ["user_pseudonym", "timestamp"],
        "ix_events_ingested_at": ["ingested_at"],
    }
    for name in ("ix_events_ip_timestamp", "ix_events_user_timestamp"):
        assert by_name[name].dialect_options["postgresql"]["where"] is not None


def test_metadata_has_only_events() -> None:
    assert set(metadata.tables) == {"events"}
