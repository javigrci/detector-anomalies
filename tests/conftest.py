"""Configuración compartida de pytest."""

import secrets
from pathlib import Path

import pytest

from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingestion"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Directorio de fixtures de ingesta (contenido ficticio)."""
    return FIXTURES


@pytest.fixture
def policy() -> IngestionPolicy:
    """Política por defecto (valores iniciales de SPEC §4.3)."""
    return IngestionPolicy()


@pytest.fixture
def pseudonymizer() -> Pseudonymizer:
    """Seudonimizador con una clave aleatoria generada al vuelo (nunca una clave fija)."""
    return Pseudonymizer(secrets.token_hex(32))


@pytest.fixture
def other_pseudonymizer() -> Pseudonymizer:
    """Seudonimizador con otra clave distinta."""
    return Pseudonymizer(secrets.token_hex(32))
