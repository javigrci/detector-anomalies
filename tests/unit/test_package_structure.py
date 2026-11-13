"""FR-000-02: la estructura de paquetes acordada es importable."""

import importlib

import pytest

PACKAGES = [
    "api",
    "core",
    "ingestion",
    "features",
    "ml",
    "scoring",
    "storage",
    "schemas",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_subpackage_is_importable(name: str) -> None:
    module = importlib.import_module(f"security_anomaly.{name}")
    assert module.__name__ == f"security_anomaly.{name}"
