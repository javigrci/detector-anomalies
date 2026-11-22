"""Las CHECK de la migración 0001 coinciden con el catálogo del incremento 1."""

import importlib.util
import re
from pathlib import Path

from security_anomaly.schemas.event import Action, EventType, Outcome

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "src/security_anomaly/storage/migrations/versions/0001_create_events.py"
)


def _load() -> object:
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_values_match_enums() -> None:
    module = _load()
    assert set(module.EVENT_TYPES) == {e.value for e in EventType}  # type: ignore[attr-defined]
    assert set(module.ACTIONS) == {a.value for a in Action}  # type: ignore[attr-defined]
    assert set(module.OUTCOMES) == {o.value for o in Outcome}  # type: ignore[attr-defined]


def test_patterns_match_event_contract() -> None:
    module = _load()
    assert re.fullmatch(module.SOURCE_PATTERN, "linux-auth")  # type: ignore[attr-defined]
    assert not re.fullmatch(module.SOURCE_PATTERN, "-bad")  # type: ignore[attr-defined]
    assert re.fullmatch(module.PSEUDONYM_PATTERN, "usr_" + "0" * 32)  # type: ignore[attr-defined]
    assert not re.fullmatch(module.PSEUDONYM_PATTERN, "user001")  # type: ignore[attr-defined]
