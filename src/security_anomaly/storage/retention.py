"""Retención y purga explícita (FR-002-19…21; research R6).

El periodo se mide desde ``ingested_at``, no desde el ``timestamp`` del evento. La purga borra por
bloques con una transacción por bloque para no bloquear la base de datos de forma prolongada.
Rol de BD: ``anomaly_maint``.
"""

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import Engine, func, select, text, tuple_
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import SQLAlchemyError

from security_anomaly.schemas.storage import PurgeResult
from security_anomaly.storage import schema
from security_anomaly.storage.config import StoragePolicy
from security_anomaly.storage.errors import translate_db_error

logger = logging.getLogger(__name__)

PURGE_CHUNK_SIZE = 5000


def resolve_retention(retention_days: int | None, policy: StoragePolicy) -> int:
    """Periodo efectivo en días; rechaza valores no positivos antes de tocar la base de datos."""
    days = policy.retention_days if retention_days is None else retention_days
    if days < 1:
        raise ValueError("retention_days debe ser al menos 1")
    return days


def compute_cutoff(now: datetime, retention_days: int) -> datetime:
    return now - timedelta(days=retention_days)


def log_purged(result: PurgeResult, seconds: float) -> None:
    """Solo recuentos, ``cutoff`` y duración (FR-002-26)."""
    logger.info(
        "events_purged",
        extra={
            "fields": {
                "retention_days": result.retention_days,
                "cutoff": result.cutoff.isoformat(),
                "dry_run": result.dry_run,
                "affected": result.affected,
                "duration_ms": round(seconds * 1000),
            }
        },
    )


def purge_events(
    engine: Engine,
    *,
    retention_days: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
    policy: StoragePolicy | None = None,
) -> PurgeResult:
    """Borra los eventos con ``ingested_at < now - retention_days``; repetirla borra 0.

    ``now`` es solo un dato de cálculo (por defecto, la hora de la base de datos) y no concede
    ningún privilegio. Con ``dry_run`` solo cuenta.
    """
    started = time.perf_counter()
    days = resolve_retention(retention_days, policy or StoragePolicy())
    if now is not None and now.tzinfo is None:
        raise ValueError("now debe tener zona horaria")
    columns = schema.events.c
    try:
        if now is None:
            with engine.connect() as connection:
                reference: datetime = connection.execute(text("SELECT now()")).scalar_one()
        else:
            reference = now
        cutoff = compute_cutoff(reference, days)
        if dry_run:
            with engine.connect() as connection:
                affected = int(
                    connection.execute(
                        select(func.count())
                        .select_from(schema.events)
                        .where(columns.ingested_at < cutoff)
                    ).scalar_one()
                )
        else:
            affected = 0
            while True:
                candidates = (
                    select(columns.source, columns.event_id)
                    .where(columns.ingested_at < cutoff)
                    .order_by(columns.ingested_at)
                    .limit(PURGE_CHUNK_SIZE)
                )
                statement = sa_delete(schema.events).where(
                    tuple_(columns.source, columns.event_id).in_(candidates)
                )
                with engine.begin() as connection:
                    deleted = connection.execute(statement).rowcount
                affected += deleted
                if deleted < PURGE_CHUNK_SIZE:
                    break
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    result = PurgeResult(retention_days=days, cutoff=cutoff, dry_run=dry_run, affected=affected)
    log_purged(result, time.perf_counter() - started)
    return result
