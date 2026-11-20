"""Riesgo ReDoS del plan: entradas patológicas se procesan rápido y como datos."""

import time
from pathlib import Path

from security_anomaly.ingestion import ingest_linux_auth
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.schemas.ingestion import RejectionCode as C


def test_hostile_lines_are_processed_in_under_a_second(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    started = time.perf_counter()
    result = ingest_linux_auth(
        fixtures_dir / "linux_auth_hostile.log",
        policy=policy,
        pseudonymizer=pseudonymizer,
        start_year=2026,
    )
    assert time.perf_counter() - started < 1
    report = result.report
    assert report.total_records == 3
    assert report.accepted == 1  # línea 3: un nombre con comillas invertidas es solo un dato
    assert [e.position for e in result.events] == [3]
    assert [(r.position, r.code) for r in report.rejections] == [
        (9, C.INVALID_IP),
        (13, C.INVALID_TIMESTAMP),
    ]
    assert report.ignored_lines == 9


def test_pathological_inputs_scale_linearly(
    tmp_path: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    lines = []
    for size in (200, 800, 1800):
        lines.append("Nov 12 10:30:00 srv sshd[1]: Failed password for " + "a " * (size // 2) + "x")
        lines.append("Nov 12 10:30:00 srv sudo:   " + "u" * 250 + " : " + "COMMAND= " * (size // 9))
        lines.append("Nov 12 10:30:00 srv sshd[1]: Invalid user " + "i" * (size // 10) + " from")
    path = tmp_path / "patho.log"
    path.write_text("\n".join(lines * 20) + "\n", encoding="utf-8")
    started = time.perf_counter()
    ingest_linux_auth(path, policy=policy, pseudonymizer=pseudonymizer, start_year=2026)
    assert time.perf_counter() - started < 1


def test_nothing_in_the_hostile_file_is_executed(
    fixtures_dir: Path, policy: IngestionPolicy, pseudonymizer: Pseudonymizer
) -> None:
    ingest_linux_auth(
        fixtures_dir / "linux_auth_hostile.log",
        policy=policy,
        pseudonymizer=pseudonymizer,
        start_year=2026,
    )
    # Solo se comprueba que el fichero que el log hostil intenta crear NO existe.
    assert not Path("/tmp/SENTINEL-EXEC").exists()  # noqa: S108
