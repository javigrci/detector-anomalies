"""FR-001-23 y FR-001-24: seudónimos estables con HMAC y fallo cerrado sin clave."""

import re
import secrets

import pytest

from security_anomaly.core.config import ConfigError
from security_anomaly.ingestion.errors import PseudonymKeyMissing
from security_anomaly.ingestion.pseudonym import Pseudonymizer

KEY = secrets.token_hex(32)
OTHER_KEY = secrets.token_hex(32)


def test_same_user_and_key_give_the_same_pseudonym() -> None:
    assert Pseudonymizer(KEY).pseudonym("user001") == Pseudonymizer(KEY).pseudonym("user001")


def test_different_users_give_different_pseudonyms() -> None:
    p = Pseudonymizer(KEY)
    assert p.pseudonym("user001") != p.pseudonym("user002")


def test_different_keys_give_different_pseudonyms() -> None:
    assert Pseudonymizer(KEY).pseudonym("user001") != Pseudonymizer(OTHER_KEY).pseudonym("user001")


def test_format_is_usr_prefix_and_32_hex() -> None:
    assert re.fullmatch(r"usr_[0-9a-f]{32}", Pseudonymizer(KEY).pseudonym("user001"))


def test_case_is_significant() -> None:
    p = Pseudonymizer(KEY)
    assert p.pseudonym("Root") != p.pseudonym("root")


def test_whitespace_and_unicode_normalization() -> None:
    p = Pseudonymizer(KEY)
    assert p.pseudonym("  user001 ") == p.pseudonym("user001")
    assert p.pseudonym("café") == p.pseudonym("café")  # NFC


def test_pseudonym_does_not_contain_the_username() -> None:
    assert "user001" not in Pseudonymizer(KEY).pseudonym("user001")


def test_short_key_is_rejected() -> None:
    with pytest.raises(ConfigError):
        Pseudonymizer("too-short")


@pytest.mark.parametrize(
    "key",
    [
        "change-me-use-at-least-32-random-characters",  # valor de .env.example
        "prefix-" + "x" * 40 + "-CHANGE-ME-suffix",
    ],
)
def test_placeholder_key_is_rejected(key: str) -> None:
    with pytest.raises(ConfigError) as exc:
        Pseudonymizer(key)
    assert key not in str(exc.value)


def test_missing_key_fails_closed_when_a_user_must_be_pseudonymized() -> None:
    p = Pseudonymizer(None)
    with pytest.raises(PseudonymKeyMissing):
        p.pseudonym("user001")
    with pytest.raises(PseudonymKeyMissing):
        p.derive_id("id", "anything")


def test_derive_id_is_deterministic_and_domain_separated() -> None:
    p = Pseudonymizer(KEY)
    assert p.derive_id("id", 1, "line") == p.derive_id("id", 1, "line")
    assert p.derive_id("id", 1, "line") != p.derive_id("user", 1, "line")
    assert p.derive_id("id", 1, "line") != p.derive_id("id", 2, "line")
    assert re.fullmatch(r"[0-9a-f]{32}", p.derive_id("id", 1, "line"))


def test_key_is_never_exposed() -> None:
    p = Pseudonymizer(KEY)
    assert KEY not in repr(p)
    assert KEY not in str(p)


def test_from_environ() -> None:
    assert Pseudonymizer.from_environ({"PSEUDONYM_KEY": KEY}).pseudonym("u") == Pseudonymizer(
        KEY
    ).pseudonym("u")
    assert Pseudonymizer.from_environ({}).has_key is False
    assert Pseudonymizer.from_environ({"PSEUDONYM_KEY": "   "}).has_key is False
    with pytest.raises(ConfigError):
        Pseudonymizer.from_environ({"PSEUDONYM_KEY": "short"})
