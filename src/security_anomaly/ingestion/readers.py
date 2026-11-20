"""Lectura de archivos JSON (lista o JSON Lines) y CSV con límites (FR-001-02, 17, 18).

Todo el contenido se trata como dato: se parsea con ``json`` y ``csv`` de la biblioteca estándar y
nunca se evalúa. Los errores de lote no incluyen contenido del archivo (``from None``).
"""

import csv
import io
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

from security_anomaly.ingestion.errors import BatchRejected
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.schemas.ingestion import BatchRejectionCode as B
from security_anomaly.schemas.ingestion import RejectionCode

Format = Literal["json", "csv"]

_JSON_SUFFIXES = {".json", ".jsonl", ".ndjson"}


@dataclass(frozen=True)
class RawRecord:
    """Un registro leído: posición 1-based y sus datos (``None`` si no es un objeto válido).

    ``forced_rejection`` lo usan los adaptadores para rechazar un registro por un motivo que solo
    ellos conocen (por ejemplo, ``missing_time_context``) sin pasar por el normalizador.
    """

    position: int
    data: dict[str, object] | None
    forced_rejection: tuple[RejectionCode, str | None] | None = None


def detect_format(path: Path) -> Format:
    suffix = path.suffix.lower()
    if suffix in _JSON_SUFFIXES:
        return "json"
    if suffix == ".csv":
        return "csv"
    raise BatchRejected(B.INVALID_FORMAT)


def read_records(
    path: Path, *, policy: IngestionPolicy, fmt: Format | None = None
) -> list[RawRecord]:
    """Lee los registros de un archivo; el formato se deduce de la extensión si no se indica."""
    text = read_text(path, policy)
    resolved = fmt or detect_format(path)
    if resolved == "csv":
        return _read_csv(text, policy)
    return _read_json(text, policy)


def read_text(path: Path, policy: IngestionPolicy) -> str:
    """Comprueba tipo y tamaño **antes** de abrir el archivo y decodifica en UTF-8 estricto."""
    try:
        info = path.stat()
    except OSError:
        raise BatchRejected(B.FILE_UNREADABLE) from None
    if not stat.S_ISREG(info.st_mode):
        raise BatchRejected(B.NOT_A_REGULAR_FILE)
    if info.st_size > policy.max_file_bytes:
        raise BatchRejected(B.FILE_TOO_LARGE, limit=policy.max_file_bytes)
    try:
        with path.open("rb") as handle:
            raw = handle.read(policy.max_file_bytes + 1)  # el archivo pudo crecer tras el stat
    except OSError:
        raise BatchRejected(B.FILE_UNREADABLE) from None
    if len(raw) > policy.max_file_bytes:
        raise BatchRejected(B.FILE_TOO_LARGE, limit=policy.max_file_bytes)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise BatchRejected(B.INVALID_ENCODING) from None


def _reject_constant(_name: str) -> NoReturn:
    raise ValueError("constante JSON no estándar")


def _loads(text: str) -> object:
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise BatchRejected(B.INVALID_FORMAT) from None


def _too_many(policy: IngestionPolicy) -> BatchRejected:
    return BatchRejected(B.TOO_MANY_EVENTS, limit=policy.max_events_per_batch)


def _read_json(text: str, policy: IngestionPolicy) -> list[RawRecord]:
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped.startswith("["):
        items = _loads(text)
        if not isinstance(items, list):
            raise BatchRejected(B.INVALID_FORMAT)
        if len(items) > policy.max_events_per_batch:
            raise _too_many(policy)
        return [
            RawRecord(index, item if isinstance(item, dict) else None)
            for index, item in enumerate(items, start=1)
        ]
    if stripped.startswith("{"):
        return _read_json_lines(text, policy)
    raise BatchRejected(B.INVALID_FORMAT)


def _read_json_lines(text: str, policy: IngestionPolicy) -> list[RawRecord]:
    lines = [
        (number, line) for number, line in enumerate(text.split("\n"), start=1) if line.strip()
    ]
    if len(lines) > policy.max_events_per_batch:
        raise _too_many(policy)
    records: list[RawRecord] = []
    for index, (number, line) in enumerate(lines):
        try:
            item = json.loads(line, parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            if index == 0:  # la primera línea no vacía decide si es JSON Lines
                raise BatchRejected(B.INVALID_FORMAT) from None
            records.append(RawRecord(number, None))
            continue
        records.append(RawRecord(number, item if isinstance(item, dict) else None))
    return records


def _read_csv(text: str, policy: IngestionPolicy) -> list[RawRecord]:
    reader = csv.reader(io.StringIO(text, newline=""))
    header: list[str] | None = None
    records: list[RawRecord] = []
    position = 0
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error:
            if header is None:
                raise BatchRejected(B.INVALID_FORMAT) from None
            position += 1
            records.append(RawRecord(position, None))
        else:
            if not row:
                continue  # línea en blanco
            if header is None:
                header = [name.strip() for name in row]
                if len(set(header)) != len(header):
                    raise BatchRejected(B.INVALID_FORMAT)
                continue
            position += 1
            records.append(
                RawRecord(
                    position,
                    dict(zip(header, row, strict=True)) if len(row) == len(header) else None,
                )
            )
        if len(records) > policy.max_events_per_batch:
            raise _too_many(policy)
    return records
