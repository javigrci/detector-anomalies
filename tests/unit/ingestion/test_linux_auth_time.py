"""FR-001-08: fecha sin año ni zona horaria, cambio de año y horas del cambio de horario."""

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from security_anomaly.ingestion import ingest_linux_auth
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.ingestion import IngestionResult
from security_anomaly.schemas.ingestion import RejectionCode as C

MADRID = ZoneInfo("Europe/Madrid")
LINE = "{ts} srv sshd[1]: Failed password for u from 192.0.2.1 port 22 ssh2\n"


def _file(tmp_path: Path, *stamps: str) -> Path:
    path = tmp_path / "auth.log"
    path.write_text("".join(LINE.format(ts=ts) for ts in stamps), encoding="utf-8")
    return path


def _run(
    path: Path,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    start_year: int | None = 2026,
    tz: object = UTC,
) -> IngestionResult:
    return ingest_linux_auth(
        path,
        policy=policy,
        pseudonymizer=pseudonymizer,
        start_year=start_year,
        tz=tz,  # type: ignore[arg-type]
    )


def test_default_zone_is_utc(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_linux_auth(
        _file(tmp_path, "Nov 12 10:30:00"),
        policy=policy,
        pseudonymizer=pseudonymizer,
        start_year=2026,
    )
    assert result.events[0].timestamp == datetime(2026, 11, 12, 10, 30, tzinfo=UTC)


def test_winter_and_summer_offsets_in_madrid(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = _file(tmp_path, "Jan 15 12:00:00", "Jul  1 12:00:00")
    events = _run(path, policy, pseudonymizer, tz=MADRID).events
    assert events[0].timestamp == datetime(2026, 1, 15, 11, 0, tzinfo=UTC)  # CET, UTC+1
    assert events[1].timestamp == datetime(2026, 7, 1, 10, 0, tzinfo=UTC)  # CEST, UTC+2


def test_an_ambiguous_hour_uses_the_first_occurrence(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    # 2026-10-25 02:30 ocurre dos veces en Madrid; se toma la primera (CEST, UTC+2).
    event = _run(_file(tmp_path, "Oct 25 02:30:00"), policy, pseudonymizer, tz=MADRID).events[0]
    assert event.timestamp == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_a_nonexistent_hour_is_rejected(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    # 2026-03-29 02:30 no existe en Madrid (se salta de 02:00 a 03:00).
    result = _run(_file(tmp_path, "Mar 29 02:30:00"), policy, pseudonymizer, tz=MADRID)
    assert result.events == ()
    assert [(r.code, r.field) for r in result.report.rejections] == [
        (C.INVALID_TIMESTAMP, "timestamp")
    ]


def test_december_to_january_adds_a_year(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = _run(fixtures_dir / "linux_auth_year_rollover.log", policy, pseudonymizer)
    stamps = [event.timestamp for event in result.events]
    assert stamps == [
        datetime(2026, 12, 31, 23, 59, 58, tzinfo=UTC),
        datetime(2027, 1, 1, 0, 0, 1, tzinfo=UTC),
        datetime(2027, 1, 1, 0, 0, 2, tzinfo=UTC),
    ]
    assert result.report.ignored_lines == 1  # CRON; aun así participa en el cambio de año
    assert result.report.out_of_order == ()


def test_the_rollover_works_even_when_only_ignored_lines_cross_the_year(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    path = tmp_path / "auth.log"
    path.write_text(
        LINE.format(ts="Dec 31 23:59:58")
        + "Jan  1 00:00:00 srv CRON[2]: (root) CMD (x)\n"
        + LINE.format(ts="Jan  1 00:00:05"),
        encoding="utf-8",
    )
    events = _run(path, policy, pseudonymizer).events
    assert events[1].timestamp == datetime(2027, 1, 1, 0, 0, 5, tzinfo=UTC)


def test_without_the_year_every_event_line_is_rejected_and_noise_is_ignored(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = _run(fixtures_dir / "linux_auth_sample.log", policy, pseudonymizer, start_year=None)
    report = result.report
    assert result.events == ()
    assert report.total_records == 10
    assert report.rejected == 10
    assert {r.code for r in report.rejections} == {C.MISSING_TIME_CONTEXT}
    assert {r.field for r in report.rejections} == {"timestamp"}
    assert report.ignored_lines == 3


def test_an_impossible_date_is_rejected_per_line(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    result = _run(_file(tmp_path, "Nov 31 10:30:00", "Nov 30 10:30:00"), policy, pseudonymizer)
    assert [event.position for event in result.events] == [2]
    assert [(r.position, r.code) for r in result.report.rejections] == [(1, C.INVALID_TIMESTAMP)]
