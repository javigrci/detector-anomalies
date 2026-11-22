"""Guardado, consulta y lectura por rango de eventos.

Contrato: specs/002-persistence/contracts/storage-api.md.

Todo valor viaja como parámetro enlazado (SQLAlchemy Core): ninguna sentencia se construye con
datos de entrada (FR-002-24). Los errores de la base de datos se traducen a ``StorageError``.
"""

import ipaddress
import logging
import time
import uuid
from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Connection, Engine, Select, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from security_anomaly.schemas.event import NormalizedEvent
from security_anomaly.schemas.storage import EventFilter, EventPage, SaveSummary, StoredEvent
from security_anomaly.storage import schema
from security_anomaly.storage.config import StoragePolicy
from security_anomaly.storage.errors import translate_db_error

logger = logging.getLogger(__name__)

#: Filas por INSERT: 1.000 filas por 10 columnas quedan muy por debajo del límite de parámetros
#: del protocolo.
INSERT_CHUNK_SIZE = 1000
_CONTENT_FIELDS = (
    "timestamp",
    "event_type",
    "action",
    "outcome",
    "user_pseudonym",
    "source_ip",
    "host",
)


def event_to_row(event: NormalizedEvent, batch_id: uuid.UUID) -> dict[str, Any]:
    """Fila almacenable: sin marcas relativas al lote ni hora de ingesta (la pone la BD)."""
    return {
        "source": event.source,
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "event_type": event.event_type.value,
        "action": event.action.value,
        "outcome": event.outcome.value,
        "user_pseudonym": event.user_pseudonym,
        "source_ip": event.source_ip,
        "host": event.host,
        "batch_id": batch_id,
    }


def dedupe_events(items: Iterable[NormalizedEvent]) -> tuple[list[NormalizedEvent], int]:
    """Colapsa repetidos (gana el primero); devuelve los únicos ordenados por clave."""
    seen: dict[tuple[str, str], NormalizedEvent] = {}
    repeated = 0
    for event in items:
        key = (event.source, event.event_id)
        if key in seen:
            repeated += 1
        else:
            seen[key] = event
    return [seen[key] for key in sorted(seen)], repeated


def chunked[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _normalized_ip(value: object) -> str | None:
    if value is None:
        return None
    return ipaddress.ip_address(str(value).split("/")[0]).compressed


def content_differs(incoming: Mapping[str, Any], stored: Mapping[str, Any]) -> bool:
    """True si algún campo de contenido del evento existente difiere del entrante."""
    for field in _CONTENT_FIELDS:
        left, right = incoming[field], stored[field]
        if field == "source_ip":
            left, right = _normalized_ip(left), _normalized_ip(right)
        if left != right:
            return True
    return False


def log_saved(summary: SaveSummary, seconds: float) -> None:
    """Solo recuentos, duración e identificador de lote (FR-002-26)."""
    logger.info(
        "events_saved",
        extra={
            "fields": {
                "batch_id": str(summary.batch_id),
                "inserted": summary.inserted,
                "existing": summary.existing,
                "existing_with_different_content": summary.existing_with_different_content,
                "duration_ms": round(seconds * 1000),
            }
        },
    )


def save_events(
    engine: Engine,
    events: Iterable[NormalizedEvent],
    *,
    batch_id: uuid.UUID | None = None,
) -> SaveSummary:
    """Guarda eventos de forma idempotente por ``(source, event_id)`` y atómica (todo o nada).

    No modifica los eventos que ya existen. Rol de BD: ``anomaly_app``.
    """
    started = time.perf_counter()
    batch = batch_id if batch_id is not None else uuid.uuid4()
    unique, repeated = dedupe_events(events)
    if not unique:
        summary = SaveSummary(
            batch_id=batch, inserted=0, existing=repeated, existing_with_different_content=0
        )
        log_saved(summary, time.perf_counter() - started)
        return summary

    rows = [event_to_row(event, batch) for event in unique]
    try:
        with engine.begin() as connection:
            inserted_keys: set[tuple[str, str]] = set()
            for chunk in chunked(rows, INSERT_CHUNK_SIZE):
                statement = (
                    pg_insert(schema.events)
                    .values(list(chunk))
                    .on_conflict_do_nothing(index_elements=["source", "event_id"])
                    .returning(schema.events.c.source, schema.events.c.event_id)
                )
                inserted_keys.update(
                    (str(source), str(event_id))
                    for source, event_id in connection.execute(statement)
                )
            existing_rows = [r for r in rows if (r["source"], r["event_id"]) not in inserted_keys]
            different = 0
            for chunk in chunked(existing_rows, INSERT_CHUNK_SIZE):
                stored = _fetch_content(connection, chunk)
                for row in chunk:
                    current = stored.get((row["source"], row["event_id"]))
                    if current is not None and content_differs(row, current):
                        different += 1
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None

    summary = SaveSummary(
        batch_id=batch,
        inserted=len(inserted_keys),
        existing=len(existing_rows) + repeated,
        existing_with_different_content=different,
    )
    log_saved(summary, time.perf_counter() - started)
    return summary


def _fetch_content(
    connection: Connection, chunk: Sequence[Mapping[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    keys = [(r["source"], r["event_id"]) for r in chunk]
    statement = select(
        schema.events.c.source,
        schema.events.c.event_id,
        schema.events.c.timestamp,
        schema.events.c.event_type,
        schema.events.c.action,
        schema.events.c.outcome,
        schema.events.c.user_pseudonym,
        func.host(schema.events.c.source_ip).label("source_ip"),
        schema.events.c.host,
    ).where(tuple_(schema.events.c.source, schema.events.c.event_id).in_(keys))
    return {
        (row.source, row.event_id): {field: getattr(row, field) for field in _CONTENT_FIELDS}
        for row in connection.execute(statement)
    }


_STORED_COLUMNS = (
    schema.events.c.source,
    schema.events.c.event_id,
    schema.events.c.timestamp,
    schema.events.c.event_type,
    schema.events.c.action,
    schema.events.c.outcome,
    schema.events.c.user_pseudonym,
    func.host(schema.events.c.source_ip).label("source_ip"),
    schema.events.c.host,
    schema.events.c.ingested_at,
    schema.events.c.batch_id,
)
_ORDER = (schema.events.c.timestamp, schema.events.c.source, schema.events.c.event_id)


def _conditions(filters: EventFilter) -> list[ColumnElement[bool]]:
    """Conjunción de los filtros presentes; todo valor es un parámetro enlazado."""
    columns = schema.events.c
    conditions: list[ColumnElement[bool]] = []
    if filters.date_from is not None:
        conditions.append(columns.timestamp >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(columns.timestamp < filters.date_to)
    if filters.source is not None:
        conditions.append(columns.source == filters.source)
    if filters.event_type is not None:
        conditions.append(columns.event_type == filters.event_type.value)
    if filters.action is not None:
        conditions.append(columns.action == filters.action.value)
    if filters.outcome is not None:
        conditions.append(columns.outcome == filters.outcome.value)
    if filters.source_ip is not None:
        conditions.append(columns.source_ip == filters.source_ip)
    if filters.user_pseudonym is not None:
        conditions.append(columns.user_pseudonym == filters.user_pseudonym)
    return conditions


def build_page_statement(filters: EventFilter, limit: int, offset: int) -> Select[Any]:
    """Una página en orden total ``timestamp, source, event_id`` (FR-002-14)."""
    return (
        select(*_STORED_COLUMNS)
        .where(*_conditions(filters))
        .order_by(*_ORDER)
        .limit(limit)
        .offset(offset)
    )


def build_count_statement(filters: EventFilter) -> Select[Any]:
    return select(func.count()).select_from(schema.events).where(*_conditions(filters))


def resolve_pagination(limit: int | None, offset: int, policy: StoragePolicy) -> tuple[int, int]:
    """Valida antes de consultar la base de datos (FR-002-15); los mensajes no llevan valores."""
    resolved = policy.query_default_limit if limit is None else limit
    if not 1 <= resolved <= policy.query_max_limit:
        raise ValueError("limit fuera de rango")
    if offset < 0:
        raise ValueError("offset no puede ser negativo")
    return resolved, offset


def log_queried(filters: EventFilter, total: int, returned: int, seconds: float) -> None:
    """Solo los nombres de los filtros usados, recuentos y duración (FR-002-26)."""
    used = sorted(name for name in type(filters).model_fields if getattr(filters, name) is not None)
    logger.info(
        "events_queried",
        extra={
            "fields": {
                "filters": used,
                "total": total,
                "returned": returned,
                "duration_ms": round(seconds * 1000),
            }
        },
    )


def query_events(
    engine: Engine,
    filters: EventFilter | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
    policy: StoragePolicy | None = None,
) -> EventPage:
    """Consulta con filtros combinables y paginación por tamaño y desplazamiento.

    Las inserciones concurrentes entre dos páginas pueden desplazar los resultados (limitación de la
    paginación por desplazamiento); para exactitud en lecturas largas se usa ``read_range``.
    Rol de BD: ``anomaly_app``.
    """
    started = time.perf_counter()
    effective = filters if filters is not None else EventFilter()
    page_size, start = resolve_pagination(limit, offset, policy or StoragePolicy())
    try:
        with engine.connect() as connection:
            total = int(connection.execute(build_count_statement(effective)).scalar_one())
            rows = connection.execute(build_page_statement(effective, page_size, start)).all()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    items = tuple(StoredEvent.model_validate(dict(row._mapping)) for row in rows)
    log_queried(effective, total, len(items), time.perf_counter() - started)
    return EventPage(items=items, total=total, limit=page_size, offset=start)


def build_range_statement(
    start: datetime,
    end: datetime,
    chunk_size: int,
    after: tuple[datetime, str, str] | None,
) -> Select[Any]:
    """Un bloque de ``[start, end)`` por paginación por clave (research R5).

    El límite superior es exclusivo y se aplica en la propia consulta: nunca sale un evento con
    ``timestamp >= end`` (Principio III).
    """
    columns = schema.events.c
    statement = select(*_STORED_COLUMNS).where(columns.timestamp >= start, columns.timestamp < end)
    if after is not None:
        statement = statement.where(
            tuple_(columns.timestamp, columns.source, columns.event_id) > tuple_(*after)
        )
    return statement.order_by(*_ORDER).limit(chunk_size)


def _iter_range(
    engine: Engine, start: datetime, end: datetime, chunk_size: int
) -> Generator[tuple[StoredEvent, ...]]:
    after: tuple[datetime, str, str] | None = None
    while True:
        try:
            with engine.connect() as connection:
                rows = connection.execute(
                    build_range_statement(start, end, chunk_size, after)
                ).all()
        except SQLAlchemyError as exc:
            raise translate_db_error(exc) from None
        if not rows:
            return
        chunk = tuple(StoredEvent.model_validate(dict(row._mapping)) for row in rows)
        yield chunk
        if len(rows) < chunk_size:
            return
        last = chunk[-1]
        after = (last.timestamp, last.source, last.event_id)


def read_range(
    engine: Engine,
    start: datetime,
    end: datetime,
    *,
    chunk_size: int = 5000,
) -> Generator[tuple[StoredEvent, ...]]:
    """Lee ``[start, end)`` en orden cronológico por bloques de como máximo ``chunk_size``.

    Sin duplicados ni saltos y con memoria acotada; cada bloque es una consulta corta. Los
    argumentos se validan al llamar, antes de abrir ninguna conexión. Rol de BD: ``anomaly_app``.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start y end deben tener zona horaria")
    if start >= end:
        raise ValueError("start debe ser anterior a end")
    if chunk_size < 1:
        raise ValueError("chunk_size debe ser al menos 1")
    return _iter_range(engine, start, end, chunk_size)
