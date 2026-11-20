"""Orquestación de la ingesta: normalización, deduplicación e informe (research R8, R9, R12)."""

import hashlib
import logging
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, tzinfo
from pathlib import Path

from security_anomaly.ingestion.adapters.linux_auth import parse_linux_auth
from security_anomaly.ingestion.errors import BatchRejected
from security_anomaly.ingestion.normalizer import normalize_record
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.ingestion.readers import Format, RawRecord, read_records, read_text
from security_anomaly.schemas.event import NormalizedEvent
from security_anomaly.schemas.ingestion import (
    BatchRejectionCode,
    Duplicate,
    IngestionReport,
    IngestionResult,
    Rejection,
)

logger = logging.getLogger("security_anomaly.ingestion")


def _fingerprint(event: NormalizedEvent) -> str:
    content = event.model_dump_json(exclude={"position", "out_of_order"})
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest_positioned(
    records: Iterable[RawRecord],
    *,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    ignored_lines: int = 0,
) -> IngestionResult:
    """Ingiere registros con su posición; ``data=None`` marca un registro que no es un objeto."""
    started = time.perf_counter()
    events: list[NormalizedEvent] = []
    rejections: list[Rejection] = []
    duplicates: list[Duplicate] = []
    seen: dict[tuple[str, str], str] = {}
    out_of_order: list[int] = []
    latest: datetime | None = None
    total = 0

    for record in records:
        position = record.position
        total += 1
        if total > policy.max_events_per_batch:
            raise BatchRejected(
                BatchRejectionCode.TOO_MANY_EVENTS, limit=policy.max_events_per_batch
            )
        if record.forced_rejection is not None:
            code, field = record.forced_rejection
            rejections.append(Rejection(position=position, code=code, field=field))
            continue
        result = normalize_record(
            record.data, position=position, policy=policy, pseudonymizer=pseudonymizer
        )
        if result.event is None:
            rejections.extend(result.rejections)
            continue
        event = result.event
        key = (event.source, event.event_id)
        fingerprint = _fingerprint(event)
        if key in seen:
            duplicates.append(
                Duplicate(position=position, content_differs=seen[key] != fingerprint)
            )
            continue
        seen[key] = fingerprint
        # Fuera de orden: anterior al mayor timestamp aceptado antes en este lote (sin tolerancia).
        # Los rechazados y los duplicados no actualizan el máximo.
        if latest is not None and event.timestamp < latest:
            out_of_order.append(position)
            event = event.model_copy(update={"out_of_order": True})
        else:
            latest = event.timestamp
        events.append(event)

    by_code = dict(sorted(Counter(rejection.code.value for rejection in rejections).items()))
    report = IngestionReport(
        total_records=total,
        accepted=len(events),
        rejected=len({rejection.position for rejection in rejections}),
        rejections=tuple(rejections),
        duplicates=tuple(duplicates),
        out_of_order=tuple(out_of_order),
        ignored_lines=ignored_lines,
        by_code=by_code,
    )
    _log_completion(report, time.perf_counter() - started)
    return IngestionResult(events=tuple(events), report=report)


def _log_completion(report: IngestionReport, seconds: float) -> None:
    """Un único registro con recuentos y duración; nunca valores de entrada (FR-001-22)."""
    logger.info(
        "ingestion_completed",
        extra={
            "fields": {
                "total_records": report.total_records,
                "accepted": report.accepted,
                "rejected": report.rejected,
                "duplicates": len(report.duplicates),
                "out_of_order": len(report.out_of_order),
                "ignored_lines": report.ignored_lines,
                "by_code": report.by_code,
                "duration_ms": round(seconds * 1000, 2),
            }
        },
    )


def ingest_records(
    records: Iterable[Mapping[str, object]],
    *,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
) -> IngestionResult:
    """Ingiere registros ya parseados; la posición es el orden de llegada, desde 1."""
    return ingest_positioned(
        (RawRecord(position, dict(data)) for position, data in enumerate(records, start=1)),
        policy=policy,
        pseudonymizer=pseudonymizer,
    )


def ingest_file(
    path: Path,
    *,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    fmt: Format | None = None,
) -> IngestionResult:
    """Lee un archivo JSON (lista o JSON Lines) o CSV y lo ingiere."""
    raw = read_records(path, policy=policy, fmt=fmt)
    return ingest_positioned(raw, policy=policy, pseudonymizer=pseudonymizer)


def ingest_linux_auth(
    path: Path,
    *,
    policy: IngestionPolicy,
    pseudonymizer: Pseudonymizer,
    start_year: int | None,
    tz: tzinfo = UTC,
) -> IngestionResult:
    """Convierte un ``auth.log`` clásico en eventos v1 y los ingiere.

    ``start_year`` es el año de la primera línea; sin él, las líneas reconocidas se rechazan con
    ``missing_time_context``. ``tz`` es la zona horaria de las fechas del archivo (UTC por defecto).
    """
    text = read_text(path, policy)
    records, ignored = parse_linux_auth(
        text, pseudonymizer=pseudonymizer, start_year=start_year, tz=tz
    )
    return ingest_positioned(
        records, policy=policy, pseudonymizer=pseudonymizer, ignored_lines=ignored
    )
