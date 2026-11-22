"""FR-002-27, ADR 0003: comportamiento observable de la rotación de `PSEUDONYM_KEY`."""

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from security_anomaly.ingestion import IngestionPolicy, Pseudonymizer, ingest_linux_auth
from security_anomaly.schemas.event import NormalizedEvent
from security_anomaly.storage import purge_events, save_events

pytestmark = pytest.mark.integration

LOG = Path(__file__).resolve().parents[2] / "fixtures" / "ingestion" / "linux_auth_sample.log"


def _ingest(key: str) -> list[NormalizedEvent]:
    result = ingest_linux_auth(
        LOG, policy=IngestionPolicy(), pseudonymizer=Pseudonymizer(key), start_year=2026
    )
    assert result.events
    return list(result.events)


def _count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM events")).scalar_one())


def test_the_same_log_with_two_keys_inserts_twice(app_engine: Engine) -> None:
    key_a, key_b = secrets.token_hex(32), secrets.token_hex(32)
    events_a, events_b = _ingest(key_a), _ingest(key_b)
    first = save_events(app_engine, events_a)
    again_same_key = save_events(app_engine, events_a)
    after_rotation = save_events(app_engine, events_b)

    assert again_same_key.inserted == 0  # con la misma clave sigue siendo idempotente
    assert after_rotation.inserted == first.inserted  # con la clave nueva no lo es
    assert after_rotation.existing == 0
    assert _count(app_engine) == 2 * first.inserted

    ids_a = {e.event_id for e in events_a}
    ids_b = {e.event_id for e in events_b}
    assert ids_a.isdisjoint(ids_b)  # los identificadores derivados cambian con la clave
    pseudonyms_a = {e.user_pseudonym for e in events_a if e.user_pseudonym}
    pseudonyms_b = {e.user_pseudonym for e in events_b if e.user_pseudonym}
    assert pseudonyms_a and pseudonyms_a.isdisjoint(pseudonyms_b)


def test_purging_before_rotating_leaves_only_the_new_key(
    app_engine: Engine, migrator_engine: Engine, maint_engine: Engine
) -> None:
    key_a, key_b = secrets.token_hex(32), secrets.token_hex(32)
    events_a, events_b = _ingest(key_a), _ingest(key_b)
    save_events(app_engine, events_a)
    # Procedimiento del ADR: detener la ingesta y purgar lo seudonimizado con la clave anterior.
    purged = purge_events(
        maint_engine, retention_days=1, now=datetime.now(UTC) + timedelta(days=30)
    )
    assert purged.affected == len(events_a)
    save_events(app_engine, events_b)
    with app_engine.connect() as connection:
        stored = set(connection.execute(text("SELECT event_id FROM events")).scalars())
    assert stored == {e.event_id for e in events_b}


def test_events_store_no_key_version_or_identifier(migrator_engine: Engine) -> None:
    with migrator_engine.connect() as connection:
        columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'events'"
                )
            ).scalars()
        )
    assert columns == {
        "source",
        "event_id",
        "timestamp",
        "event_type",
        "action",
        "outcome",
        "user_pseudonym",
        "source_ip",
        "host",
        "ingested_at",
        "batch_id",
    }
