"""FR-002-19, 21: lógica pura de la retención (sin base de datos)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from security_anomaly.storage.config import StoragePolicy
from security_anomaly.storage.retention import (
    PURGE_CHUNK_SIZE,
    compute_cutoff,
    purge_events,
    resolve_retention,
)

NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)


def test_cutoff_is_now_minus_the_period() -> None:
    assert compute_cutoff(NOW, 90) == NOW - timedelta(days=90)
    assert compute_cutoff(NOW, 1) == NOW - timedelta(days=1)


def test_the_period_defaults_to_the_policy() -> None:
    assert resolve_retention(None, StoragePolicy()) == 90
    assert resolve_retention(None, StoragePolicy(retention_days=30)) == 30
    assert resolve_retention(7, StoragePolicy(retention_days=30)) == 7


@pytest.mark.parametrize("days", [0, -1, -90])
def test_a_non_positive_period_is_rejected(days: int) -> None:
    with pytest.raises(ValueError, match="retention_days"):
        resolve_retention(days, StoragePolicy())


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("days", [0, -1])
def test_invalid_period_never_touches_the_database(days: int, dry_run: bool) -> None:
    engine = MagicMock()
    with pytest.raises(ValueError, match="retention_days"):
        purge_events(engine, retention_days=days, dry_run=dry_run)
    engine.connect.assert_not_called()
    engine.begin.assert_not_called()


def test_naive_now_is_rejected() -> None:
    engine = MagicMock()
    with pytest.raises(ValueError, match="now"):
        purge_events(engine, now=datetime(2026, 1, 1))
    engine.connect.assert_not_called()


def test_blocks_are_of_five_thousand() -> None:
    assert PURGE_CHUNK_SIZE == 5000
