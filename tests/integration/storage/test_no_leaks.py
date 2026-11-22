"""SC-006, FR-002-25, 26: ningún valor sensible sale en datos, resultados, errores, logs ni CLI."""

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, text

from security_anomaly.ingestion import IngestionPolicy, Pseudonymizer, ingest_records
from security_anomaly.storage import (
    EventFilter,
    StorageError,
    purge_events,
    query_events,
    read_range,
    save_events,
)
from security_anomaly.storage import __main__ as cli

pytestmark = pytest.mark.integration

USER = "SENTINEL-USER-mallory"
PASSWORD = "SENTINEL-PASSWORD-zzz"
HOST = "SENTINEL-HOST-leak"


def _records() -> list[dict[str, str]]:
    return [
        {
            "event_id": f"leak-{i}",
            "timestamp": "2026-01-01T10:00:00+00:00",
            "source": "linux-auth",
            "event_type": "authentication",
            "action": "login",
            "outcome": "failure",
            "username": USER,
            "source_ip": "192.0.2.10",
            "host": f"srv-demo-0{i}",
        }
        for i in range(3)
    ]


def test_no_sensitive_value_leaves_any_operation(
    app_engine: Engine,
    migrator_engine: Engine,
    maint_engine: Engine,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pseudonymizer = Pseudonymizer(secrets.token_hex(32))
    ingested = ingest_records(_records(), policy=IngestionPolicy(), pseudonymizer=pseudonymizer)
    outputs: list[str] = []
    with caplog.at_level(logging.DEBUG):
        summary = save_events(app_engine, ingested.events)
        outputs.append(summary.model_dump_json())
        page = query_events(app_engine, EventFilter(source="linux-auth"))
        outputs.append(page.model_dump_json())
        for chunk in read_range(
            app_engine, datetime(2025, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)
        ):
            outputs.extend(event.model_dump_json() for event in chunk)
        outputs.append(purge_events(maint_engine, retention_days=1, dry_run=True).model_dump_json())
        outputs.append(
            purge_events(
                maint_engine, retention_days=1, now=datetime.now(UTC) + timedelta(days=5)
            ).model_dump_json()
        )

        # Errores controlados: valor sentinela en una fila inválida y base de datos caída.
        bad = ingested.events[0].model_copy(update={"event_id": "bad", "host": HOST + "x" * 300})
        with pytest.raises(StorageError) as integrity:
            save_events(app_engine, [bad])
        dead = create_engine(
            app_engine.url.set(port=1, password=PASSWORD), connect_args={"connect_timeout": 1}
        )
        try:
            with pytest.raises(StorageError) as unavailable:
                save_events(dead, ingested.events)
        finally:
            dead.dispose()
        for error in (integrity.value, unavailable.value):
            outputs.append(f"{error!s} {error!r} {error.args!r}")

        # CLI: configuración inválida y error de base de datos.
        bad_url = f"postgresql+psycopg://anomaly_maint:{PASSWORD}@127.0.0.1:1/db"
        cli.main(["purge"], {"MAINTENANCE_DATABASE_URL": bad_url})
        cli.main(["purge"], {"MAINTENANCE_DATABASE_URL": "mysql://u:" + PASSWORD + "@h/db"})
        cli.main(["purge", "--days", USER], {"MAINTENANCE_DATABASE_URL": bad_url})

    captured = capsys.readouterr()
    outputs.extend([captured.out, captured.err, caplog.text])
    with migrator_engine.connect() as connection:
        outputs.extend(connection.execute(text("SELECT events::text FROM events")).scalars())
        outputs.append(
            json.dumps(
                list(
                    connection.execute(
                        text("SELECT column_name FROM information_schema.columns")
                    ).scalars()
                )
            )
        )

    blob = "\n".join(outputs)
    for sentinel in (USER, PASSWORD, "SENTINEL-HOST-leak", "SENTINEL"):
        assert sentinel not in blob, sentinel
    assert "events_saved" in caplog.text and "events_purged" in caplog.text
