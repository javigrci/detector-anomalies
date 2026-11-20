"""FR-001-06, 07 y 10: conversión de `auth.log` clásico a eventos v1."""

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from security_anomaly.ingestion import ingest_linux_auth
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.event import Action, EventType, NormalizedEvent, Outcome
from security_anomaly.schemas.ingestion import IngestionResult

MADRID = ZoneInfo("Europe/Madrid")
SENTINELS = [
    "SENTINEL-COMMAND",
    "SENTINEL-PWD",
    "SENTINEL-KEY-FP",
    "user001",
    "user002",
    "user003",
    "user004",
    "/usr/bin/cat",
    "/home/user",
]


def _ingest(
    path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer, **kwargs: object
) -> IngestionResult:
    options: dict[str, object] = {"start_year": 2026, "tz": MADRID, **kwargs}
    return ingest_linux_auth(path, policy=policy, pseudonymizer=pseudonymizer, **options)  # type: ignore[arg-type]


def _by_position(result: IngestionResult) -> dict[int, NormalizedEvent]:
    return {event.position: event for event in result.events}


def test_ingest_linux_auth_is_exported() -> None:
    from security_anomaly.ingestion import ingest_linux_auth as exported

    assert callable(exported)


def test_sample_counts(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    report = _ingest(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer).report
    assert report.total_records == 10
    assert report.accepted == 10
    assert report.rejected == 0
    assert report.ignored_lines == 3  # PAM de sudo, CRON y systemd-logind
    assert report.duplicates == ()


@pytest.mark.parametrize(
    ("position", "event_type", "action", "outcome", "ip"),
    [
        (1, EventType.AUTHENTICATION, Action.LOGIN, Outcome.SUCCESS, "192.0.2.45"),
        (2, EventType.AUTHENTICATION, Action.LOGIN, Outcome.FAILURE, "192.0.2.45"),
        (3, EventType.AUTHENTICATION, Action.LOGIN, Outcome.FAILURE, "198.51.100.9"),
        (4, EventType.AUTHENTICATION, Action.INVALID_USER, Outcome.FAILURE, "198.51.100.9"),
        (5, EventType.AUTHENTICATION, Action.LOGIN, Outcome.SUCCESS, "2001:db8::5"),
        (6, EventType.PRIVILEGE_ESCALATION, Action.SUDO, Outcome.SUCCESS, None),
        (8, EventType.PRIVILEGE_ESCALATION, Action.SUDO, Outcome.FAILURE, None),
        (9, EventType.PRIVILEGE_ESCALATION, Action.SUDO, Outcome.FAILURE, None),
        (12, EventType.AUTHENTICATION, Action.LOGIN, Outcome.FAILURE, "192.0.2.45"),
        (13, EventType.AUTHENTICATION, Action.LOGIN, Outcome.FAILURE, "192.0.2.45"),
    ],
)
def test_each_line_type_maps_to_the_expected_event(
    position: int,
    event_type: EventType,
    action: Action,
    outcome: Outcome,
    ip: str | None,
    fixtures_dir: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
) -> None:
    event = _by_position(_ingest(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer))[
        position
    ]
    assert event.event_type == event_type
    assert event.action == action
    assert event.outcome == outcome
    assert event.source_ip == ip
    assert event.source == "linux-auth"
    assert event.host == "srv-demo-01"
    assert event.user_pseudonym is not None


def test_ignored_lines_produce_no_event(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    events = _by_position(_ingest(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer))
    assert {7, 10, 11}.isdisjoint(events)


def test_timestamps_use_the_given_year_and_zone(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    events = _by_position(_ingest(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer))
    assert events[1].timestamp == datetime(2026, 11, 12, 9, 30, tzinfo=UTC)  # CET = UTC+1


def test_same_user_gets_the_same_pseudonym_across_lines(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    events = _by_position(_ingest(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer))
    assert events[1].user_pseudonym == events[2].user_pseudonym == events[12].user_pseudonym
    assert events[1].user_pseudonym != events[5].user_pseudonym


def test_sudo_keeps_no_command_directory_or_target_user(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = _ingest(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer)
    outputs = result.to_canonical_json() + repr(result)
    for sentinel in SENTINELS:
        assert sentinel not in outputs, sentinel


def test_rhel_variant_and_empty_user(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = _ingest(fixtures_dir / "linux_auth_rhel.log", policy, pseudonymizer)
    events = _by_position(result)
    assert result.report.total_records == 5
    assert result.report.ignored_lines == 1  # PAM de sshd
    assert events[1].action == Action.LOGIN
    assert events[1].outcome == Outcome.FAILURE
    assert events[1].source_ip == "203.0.113.5"
    assert events[3].outcome == Outcome.SUCCESS
    assert events[4].action == Action.SUDO
    assert events[6].action == Action.INVALID_USER
    assert events[6].user_pseudonym is None  # "Invalid user  from …" sin nombre
    assert events[6].host == "rhel-demo-01"
    assert result.report.out_of_order == (6,)  # "Nov  5" es anterior a "Nov 12"


def test_a_single_digit_day_is_parsed(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = tmp_path / "auth.log"
    path.write_text(
        "Nov  5 09:05:09 h sshd[1]: Failed password for u from 192.0.2.1 port 22 ssh2\n"
    )
    event = _ingest(path, policy, pseudonymizer, tz=UTC).events[0]
    assert event.timestamp == datetime(2026, 11, 5, 9, 5, 9, tzinfo=UTC)


def test_the_new_sshd_session_process_name_is_accepted(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = tmp_path / "auth.log"
    path.write_text(
        "Nov 12 10:30:00 h sshd-session[1]: Failed password for u from 192.0.2.1 port 22 ssh2\n"
    )
    assert _ingest(path, policy, pseudonymizer, tz=UTC).report.accepted == 1
