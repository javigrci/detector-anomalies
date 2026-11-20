"""FR-001-30: la API pública coincide con contracts/ingestion-api.md.

Es la comprobación final del contrato: las aserciones de importación de cada función ya se
escribieron antes, junto a sus historias.
"""

import inspect
import re
from datetime import UTC
from pathlib import Path

import security_anomaly.ingestion as ingestion
from security_anomaly.schemas.ingestion import BatchRejectionCode, RejectionCode

CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "specs"
    / "001-ingestion"
    / "contracts"
    / "ingestion-api.md"
).read_text(encoding="utf-8")


def _documented_exports() -> set[str]:
    block = CONTRACT.split("## Exportaciones", 1)[1].split("## Garantías", 1)[0]
    return set(re.findall(r"`([A-Za-z_]+)`", block.split("exporta exactamente:", 1)[1]))


def _codes(heading_pattern: str) -> set[str]:
    section = re.search(heading_pattern, CONTRACT, flags=re.DOTALL)
    assert section is not None
    return set(re.findall(r"`([a-z_]+)`", section.group(1)))


def test_exports_are_exactly_the_documented_ones() -> None:
    documented = _documented_exports()
    assert documented, "el contrato debe listar las exportaciones"
    assert set(ingestion.__all__) == documented
    for name in documented:
        assert hasattr(ingestion, name), name


def _parameters(function: object) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(function).parameters)  # type: ignore[arg-type]


def test_ingest_file_signature() -> None:
    params = _parameters(ingestion.ingest_file)
    assert list(params) == ["path", "policy", "pseudonymizer", "fmt"]
    assert params["policy"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["pseudonymizer"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["fmt"].default is None


def test_ingest_records_signature() -> None:
    params = _parameters(ingestion.ingest_records)
    assert list(params) == ["records", "policy", "pseudonymizer"]
    assert params["policy"].kind is inspect.Parameter.KEYWORD_ONLY


def test_ingest_linux_auth_signature() -> None:
    params = _parameters(ingestion.ingest_linux_auth)
    assert list(params) == ["path", "policy", "pseudonymizer", "start_year", "tz"]
    assert params["start_year"].default is inspect.Parameter.empty  # obligatorio (puede ser None)
    assert params["start_year"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["tz"].default is UTC


def test_generate_synthetic_signature_has_the_policy_parameter() -> None:
    params = _parameters(ingestion.generate_synthetic)
    assert list(params) == ["config", "policy"]
    assert params["policy"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["policy"].default is None


def test_documented_rejection_codes_match_the_enums() -> None:
    batch = _codes(r"Códigos de lote:(.*?)\.\n")
    record = _codes(r"## Códigos de rechazo de registro(.*?)Estables")
    assert batch == {code.value for code in BatchRejectionCode}
    assert record == {code.value for code in RejectionCode}


def test_every_documented_function_appears_in_the_contract() -> None:
    for name in ("ingest_file", "ingest_records", "ingest_linux_auth", "generate_synthetic"):
        assert f"{name}(" in CONTRACT, name
