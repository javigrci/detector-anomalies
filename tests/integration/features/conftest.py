"""Fixtures de la integración de características: tabla `events` vacía antes de cada test."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text


@pytest.fixture(autouse=True)
def empty_events(migrator_engine: Engine) -> Iterator[None]:
    with migrator_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE events"))
    yield
