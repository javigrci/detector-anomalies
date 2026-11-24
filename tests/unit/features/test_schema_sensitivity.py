"""SC-007: cualquier cambio de definición, orden, tipo, ámbito o ventana cambia la huella."""

import pytest

from security_anomaly.features.schema import FEATURE_SCHEMA
from security_anomaly.schemas.features import FeatureDefinition, FeatureSchema

DEFS = FEATURE_SCHEMA.definitions


def _schema(
    definitions: tuple[FeatureDefinition, ...] | None = None, **changes: int
) -> FeatureSchema:
    return FeatureSchema(
        version=changes.get("version", FEATURE_SCHEMA.version),
        window_seconds=changes.get("window_seconds", FEATURE_SCHEMA.window_seconds),
        definitions=definitions if definitions is not None else DEFS,
    )


def _replace(index: int, **update: str) -> FeatureSchema:
    changed = DEFS[index].model_copy(update=update)
    return _schema((*DEFS[:index], changed, *DEFS[index + 1 :]))


@pytest.mark.parametrize("index", range(len(DEFS)))
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "renamed"),
        ("kind", "category"),
        ("scope", "indicator"),
        ("definition", "una definicion distinta"),
    ],
)
def test_changing_any_field_of_any_feature_changes_the_fingerprint(
    index: int, field: str, value: str
) -> None:
    if getattr(DEFS[index], field) == value:
        value += "-x"
    assert _replace(index, **{field: value}).fingerprint != FEATURE_SCHEMA.fingerprint


@pytest.mark.parametrize("index", range(len(DEFS) - 1))
def test_swapping_two_neighbours_changes_the_fingerprint(index: int) -> None:
    swapped = list(DEFS)
    swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
    assert _schema(tuple(swapped)).fingerprint != FEATURE_SCHEMA.fingerprint


def test_window_version_and_membership_change_the_fingerprint() -> None:
    base = FEATURE_SCHEMA.fingerprint
    assert _schema(window_seconds=600).fingerprint != base
    assert _schema(version=2).fingerprint != base
    assert _schema(DEFS[:-1]).fingerprint != base  # quitar
    extra = FeatureDefinition(name="extra", kind="int", scope="window", definition="una mas")
    assert _schema((*DEFS, extra)).fingerprint != base  # añadir


def test_all_the_variants_are_different_from_each_other() -> None:
    variants = {_replace(i, definition=f"cambio {i}").fingerprint for i in range(len(DEFS))}
    assert len(variants) == len(DEFS)
