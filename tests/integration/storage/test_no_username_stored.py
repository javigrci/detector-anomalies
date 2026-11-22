"""FR-002-02, 12, SC-006: el nombre de usuario original no existe en la base de datos."""

import secrets

import pytest
from sqlalchemy import Engine, text

from security_anomaly.ingestion import IngestionPolicy, ingest_records
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.storage import save_events

pytestmark = pytest.mark.integration

SENTINEL_USER = "SENTINEL-USER-alice"


def _record(event_id: str, **overrides: str) -> dict[str, str]:
    record = {
        "event_id": event_id,
        "timestamp": "2026-01-01T10:00:00+00:00",
        "source": "linux-auth",
        "event_type": "authentication",
        "action": "login",
        "outcome": "failure",
        "username": SENTINEL_USER,
        "source_ip": "192.0.2.10",
        "host": "srv-demo-01",
    }
    record.update(overrides)
    return record


def test_only_the_pseudonym_reaches_the_database(
    app_engine: Engine, migrator_engine: Engine
) -> None:
    pseudonymizer = Pseudonymizer(secrets.token_hex(32))
    result = ingest_records(
        [_record("e1"), _record("e2")], policy=IngestionPolicy(), pseudonymizer=pseudonymizer
    )
    save_events(app_engine, result.events)
    with migrator_engine.connect() as connection:
        dump = connection.execute(text("SELECT events::text FROM events")).scalars().all()
        columns = (
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'events'"
                )
            )
            .scalars()
            .all()
        )
    assert dump and all(SENTINEL_USER not in row for row in dump)
    assert "username" not in columns
    with migrator_engine.connect() as connection:
        pseudonyms = connection.execute(text("SELECT user_pseudonym FROM events")).scalars().all()
    assert all(p.startswith("usr_") and len(p) == 36 for p in pseudonyms)


def test_rejected_records_are_not_stored(app_engine: Engine) -> None:
    pseudonymizer = Pseudonymizer(secrets.token_hex(32))
    records = [
        _record("good-1"),
        _record("bad-1", outcome="maybe"),
        _record("good-2"),
        _record("bad-2", timestamp="no es una fecha"),
    ]
    result = ingest_records(records, policy=IngestionPolicy(), pseudonymizer=pseudonymizer)
    assert result.report.rejected == 2
    summary = save_events(app_engine, result.events)
    assert summary.inserted == 2
    with app_engine.connect() as connection:
        ids = set(connection.execute(text("SELECT event_id FROM events")).scalars())
    assert ids == {"good-1", "good-2"}
