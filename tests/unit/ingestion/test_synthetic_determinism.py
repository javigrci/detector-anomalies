"""FR-001-26 y FR-001-29: el generador es reproducible y respeta el máximo del dataset."""

import pytest
from pydantic import ValidationError

from security_anomaly.ingestion import SyntheticConfig, SyntheticDataset, generate_synthetic
from security_anomaly.ingestion.policy import IngestionPolicy


def _config(**overrides: object) -> SyntheticConfig:
    values: dict[str, object] = {
        "seed": 42,
        "n_events": 500,
        "burst_count": 1,
        "burst_size": 20,
        "atypical_hour_count": 5,
        "missing_ip_count": 5,
        "duplicate_count": 5,
        "out_of_order_count": 5,
        "new_category_count": 5,
        **overrides,
    }
    return SyntheticConfig.model_validate(values)


def test_public_names_are_exported() -> None:
    assert callable(generate_synthetic)
    assert SyntheticConfig is not None
    assert SyntheticDataset is not None


def test_same_configuration_gives_identical_datasets() -> None:
    first = generate_synthetic(_config())
    second = generate_synthetic(_config())
    assert first.events == second.events
    assert first.labels == second.labels
    assert first.model_dump_json() == second.model_dump_json()


def test_different_seeds_give_different_datasets() -> None:
    assert generate_synthetic(_config(seed=1)).events != generate_synthetic(_config(seed=2)).events


def test_the_dataset_has_exactly_n_events() -> None:
    assert len(generate_synthetic(_config(n_events=321)).events) == 321


def test_more_events_than_the_default_dataset_maximum_is_rejected() -> None:
    with pytest.raises(ValueError, match="máximo"):
        generate_synthetic(_config(n_events=100_001))


def test_the_maximum_comes_from_the_policy() -> None:
    small = IngestionPolicy(max_events_per_dataset=500)
    assert len(generate_synthetic(_config(n_events=500), policy=small).events) == 500
    with pytest.raises(ValueError, match="máximo"):
        generate_synthetic(_config(n_events=501), policy=small)


@pytest.mark.parametrize(
    "overrides",
    [
        {"n_events": 50, "burst_count": 1, "burst_size": 100},  # la ráfaga no cabe
        {"n_events": 30, "duplicate_count": 30},  # no queda ningún evento normal
        {"n_events": 100, "out_of_order_count": 500},
        {"n_events": 100, "new_category_count": 500},
    ],
)
def test_incoherent_configurations_are_rejected(overrides: dict[str, object]) -> None:
    config = _config(
        **{
            "burst_count": 0,
            "atypical_hour_count": 0,
            "missing_ip_count": 0,
            "duplicate_count": 0,
            "out_of_order_count": 0,
            "new_category_count": 0,
            **overrides,
        }
    )
    with pytest.raises(ValueError, match="configuración"):
        generate_synthetic(config)


@pytest.mark.parametrize(
    "overrides", [{"n_events": 0}, {"n_events": -1}, {"burst_count": -1}, {"n_users": 0}]
)
def test_invalid_field_values_fail_validation(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _config(**overrides)
