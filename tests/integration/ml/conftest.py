"""Fixtures de la integración del entrenamiento: tablas vacías antes de cada test."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from security_anomaly.ml.config import MlSettings
from security_anomaly.schemas.event import NormalizedEvent
from security_anomaly.storage import save_events
from tests.ml_factory import synthetic_vectors


@pytest.fixture(autouse=True)
def empty_tables(migrator_engine: Engine) -> Iterator[None]:
    with migrator_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE events"))
        found = connection.execute(text("SELECT to_regclass('public.model_versions')"))
        if found.scalar_one() is not None:
            connection.execute(text("TRUNCATE TABLE model_versions, training_runs CASCADE"))
    yield


@dataclass(frozen=True)
class LoadedData:
    start: datetime
    end: datetime
    history_start: datetime
    labels: Mapping[str, str]
    events: list[NormalizedEvent]


def load_events(
    engine: Engine, events: list[NormalizedEvent], labels: Mapping[str, str]
) -> LoadedData:
    save_events(engine, events)
    first = min(e.timestamp for e in events)
    last = max(e.timestamp for e in events)
    return LoadedData(
        start=first,
        end=last + timedelta(seconds=1),
        history_start=first - timedelta(hours=1),
        labels=labels,
        events=events,
    )


@pytest.fixture
def loaded(app_engine: Engine) -> LoadedData:
    data = synthetic_vectors(2, 1500)
    return load_events(app_engine, data.events, data.labels)


@pytest.fixture
def settings(tmp_path: Path) -> MlSettings:
    return MlSettings(model_dir=tmp_path)
