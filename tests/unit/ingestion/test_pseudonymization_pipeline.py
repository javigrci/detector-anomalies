"""FR-001-23: seudónimos estables a través del pipeline."""

import secrets
from typing import Any

from security_anomaly.ingestion import ingest_records
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer


def _event(n: int, username: str | None) -> dict[str, Any]:
    return {
        "event_id": f"e{n}",
        "timestamp": "2026-11-12T10:30:00Z",
        "source": "linux-auth",
        "event_type": "authentication",
        "action": "login",
        "outcome": "failure",
        "username": username,
    }


def _pseudonyms(
    names: list[str | None], policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> list[str | None]:
    records = [_event(n, name) for n, name in enumerate(names)]
    result = ingest_records(records, policy=policy, pseudonymizer=pseudonymizer)
    return [event.user_pseudonym for event in result.events]


def test_same_user_gets_the_same_pseudonym_across_events_and_calls(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    first = _pseudonyms(["user001", "user002", "user001"], policy, pseudonymizer)
    second = _pseudonyms(["user001"], policy, pseudonymizer)
    assert first[0] == first[2] == second[0]


def test_different_users_get_different_pseudonyms(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    pseudonyms = _pseudonyms(["user001", "user002", "user003"], policy, pseudonymizer)
    assert len(set(pseudonyms)) == 3


def test_another_key_gives_another_pseudonym(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer, other_pseudonymizer: Pseudonymizer
) -> None:
    assert _pseudonyms(["user001"], policy, pseudonymizer) != _pseudonyms(
        ["user001"], policy, other_pseudonymizer
    )


def test_whitespace_and_unicode_variants_share_a_pseudonym(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    pseudonyms = _pseudonyms(["café", "  café ", "café\t"], policy, pseudonymizer)
    assert len(set(pseudonyms)) == 1


def test_case_differences_give_different_pseudonyms(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    pseudonyms = _pseudonyms(["Root", "root", "ROOT"], policy, pseudonymizer)
    assert len(set(pseudonyms)) == 3


def test_a_user_less_event_has_no_pseudonym(
    policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    assert _pseudonyms([None, "", "  "], policy, pseudonymizer) == [None, None, None]


def test_the_pseudonym_does_not_reveal_the_user_even_with_a_known_key_length(
    policy: IngestionPolicy,
) -> None:
    key = secrets.token_hex(32)
    first = _pseudonyms(["alice"], policy, Pseudonymizer(key))[0]
    assert first is not None
    assert "alice" not in first
    assert first.startswith("usr_")
