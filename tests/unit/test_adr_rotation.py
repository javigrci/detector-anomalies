"""SC-008, FR-002-27: el ADR 0003 existe y cubre los efectos de rotar `PSEUDONYM_KEY`."""

from pathlib import Path

ADR = Path(__file__).resolve().parents[2] / "docs" / "decisions" / "0003-rotacion-pseudonym-key.md"


def _text() -> str:
    return ADR.read_text().lower()


def test_the_adr_exists_and_is_accepted() -> None:
    assert ADR.is_file()
    assert "aceptada" in _text()


def test_it_covers_the_three_effects() -> None:
    text = _text()
    assert "seudónimos" in text
    assert "event_id" in text and "adaptador" in text
    assert "idempotencia" in text or "idempotente" in text


def test_it_states_that_names_cannot_be_reseudonymized() -> None:
    text = _text()
    assert "reseudonimizar" in text
    assert "no se guarda" in text or "nunca se guarda" in text


def test_it_requires_purging_before_rotating_and_states_the_cost() -> None:
    text = _text()
    assert "purgar" in text
    assert "antes" in text
    assert "coste" in text
    assert "procedimiento" in text


def test_it_rules_out_storing_a_key_version() -> None:
    text = _text()
    assert "versión" in text and "clave" in text
    assert "única clave" in text
