"""FR-002-10, 25: un fallo a mitad de un lote no deja nada y no revela valores."""

import pytest
from sqlalchemy import Engine, create_engine, text

from security_anomaly.storage import StorageError, save_events
from tests.storage_factory import make_event, make_events

pytestmark = pytest.mark.integration


def _count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM events")).scalar_one())


def test_failure_in_the_last_chunk_stores_nothing(app_engine: Engine) -> None:
    # Más de un bloque de 1.000 filas; la última viola la CHECK del `host` (> 256 caracteres).
    good = make_events(1500)
    bad = make_event(1500, event_id="zzz-bad", host="SENTINEL-HOST-" + "x" * 300)
    with pytest.raises(StorageError) as exc:
        save_events(app_engine, [*good, bad])
    assert exc.value.code == "integrity"
    assert _count(app_engine) == 0


def test_error_text_has_no_values_or_credentials(app_engine: Engine) -> None:
    bad = make_event(1, host="SENTINEL-HOST-" + "x" * 300, user_pseudonym="usr_" + "a" * 32)
    with pytest.raises(StorageError) as exc:
        save_events(app_engine, [bad])
    text_ = f"{exc.value!s} {exc.value!r} {exc.value.args!r}"
    assert "SENTINEL" not in text_
    assert "INSERT" not in text_
    assert "usr_" not in text_
    assert exc.value.__cause__ is None


def test_unavailable_database_gives_a_controlled_error(app_engine: Engine) -> None:
    url = app_engine.url.set(port=1, password="SENTINEL-PASSWORD-x")
    dead = create_engine(url, connect_args={"connect_timeout": 1})
    try:
        with pytest.raises(StorageError) as exc:
            save_events(dead, make_events(3))
    finally:
        dead.dispose()
    assert exc.value.code == "unavailable"
    assert "SENTINEL" not in f"{exc.value!s} {exc.value!r}"
    assert exc.value.__cause__ is None
