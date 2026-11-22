"""FR-002-20, 22: la purga con las credenciales de la aplicación se deniega."""

import pytest
from sqlalchemy import Engine, text

from security_anomaly.storage import StorageError, purge_events, save_events
from tests.storage_factory import make_events

pytestmark = pytest.mark.integration


def test_the_application_role_cannot_purge(app_engine: Engine, migrator_engine: Engine) -> None:
    save_events(app_engine, make_events(10))
    with migrator_engine.begin() as connection:
        connection.execute(text("UPDATE events SET ingested_at = now() - interval '200 days'"))
    with pytest.raises(StorageError) as exc:
        purge_events(app_engine, retention_days=90)
    assert exc.value.code == "permission_denied"
    with app_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM events")).scalar_one() == 10
