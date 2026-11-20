"""Adaptador de ``auth.log`` clásico de Linux (formato syslog) hacia eventos v1 (FR-001-06…10).

Solo se reconocen cuatro familias de mensaje: inicio de sesión SSH correcto, inicio de sesión SSH
fallido, usuario inválido y ``sudo`` correcto o fallido. Todo lo demás se ignora y se cuenta aparte.

Seguridad (research R7):

- Expresiones regulares **ancladas** (``fullmatch``) y con cuantificadores acotados: sin retroceso
  catastrófico. Las líneas de más de 2.048 caracteres se ignoran antes de aplicar ninguna.
- Del ``sudo`` solo se conserva el usuario: el comando, el directorio y el usuario destino se
  descartan al leer.
- Los identificadores se derivan con HMAC y la clave del seudonimizador, no con un hash simple: un
  hash sin clave permitiría confirmar un usuario adivinado probando candidatos.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.ingestion.readers import RawRecord
from security_anomaly.schemas.ingestion import RejectionCode

SOURCE = "linux-auth"
MAX_LINE_LENGTH = 2048

_MONTHS = {
    name: number
    for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )
}
_IP = r"[0-9A-Fa-f:.]{2,45}"

_HEADER = re.compile(
    r"(?P<mon>[A-Z][a-z]{2}) {1,2}(?P<day>\d{1,2}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) "
    r"(?P<host>\S{1,255}) (?P<proc>[A-Za-z0-9_./-]{1,64})(?:\[\d{1,10}\])?: (?P<msg>.*)"
)
_ACCEPTED = re.compile(
    rf"Accepted \S{{1,40}} for (?P<user>\S{{1,256}}) from (?P<ip>{_IP}) port \d{{1,5}}(?: .*)?"
)
_FAILED = re.compile(
    rf"Failed \S{{1,40}} for (?:invalid user )?(?P<user>\S{{1,256}}) from (?P<ip>{_IP}) "
    rf"port \d{{1,5}}(?: .*)?"
)
_INVALID_USER = re.compile(
    rf"Invalid user (?P<user>\S{{0,256}}) from (?P<ip>{_IP})(?: port \d{{1,5}})?(?: .*)?"
)
_SUDO_FAILED = re.compile(
    r" {0,16}(?P<user>[^\s:]{1,256}) : "
    r"(?:\d{1,3} incorrect password attempts|user NOT in sudoers) ;.*"
)
_SUDO_OK = re.compile(r" {0,16}(?P<user>[^\s:]{1,256}) : (?:TTY=\S{1,64} ; )?PWD=.*COMMAND=.*")


@dataclass(frozen=True)
class _Parsed:
    event_type: str
    action: str
    outcome: str
    username: str | None
    source_ip: str | None


def _parse_message(process: str, message: str) -> _Parsed | None:
    if process in {"sshd", "sshd-session"}:
        if match := _ACCEPTED.fullmatch(message):
            return _Parsed("authentication", "login", "success", match["user"], match["ip"])
        if match := _FAILED.fullmatch(message):
            return _Parsed("authentication", "login", "failure", match["user"], match["ip"])
        if match := _INVALID_USER.fullmatch(message):
            return _Parsed(
                "authentication", "invalid_user", "failure", match["user"] or None, match["ip"]
            )
    elif process == "sudo":
        if match := _SUDO_FAILED.fullmatch(message):
            return _Parsed("privilege_escalation", "sudo", "failure", match["user"], None)
        if match := _SUDO_OK.fullmatch(message):
            return _Parsed("privilege_escalation", "sudo", "success", match["user"], None)
    return None


def _to_utc(naive: datetime, tz: tzinfo) -> datetime | None:
    """Convierte una hora local a UTC; ``None`` si no existe (salto de horario de verano)."""
    utc = naive.replace(tzinfo=tz).astimezone(UTC)
    if utc.astimezone(tz).replace(tzinfo=None) != naive:
        return None
    return utc


def parse_linux_auth(
    text: str,
    *,
    pseudonymizer: Pseudonymizer,
    start_year: int | None,
    tz: tzinfo = UTC,
) -> tuple[list[RawRecord], int]:
    """Convierte el texto de un ``auth.log`` en registros v1 y cuenta las líneas ignoradas.

    ``start_year`` es el año de la primera línea; sin él, las líneas reconocidas se rechazan con
    ``missing_time_context`` (no se adivina). La posición de cada registro es el número de línea.
    """
    records: list[RawRecord] = []
    ignored = 0
    year = start_year
    previous_month: int | None = None

    for number, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue
        if len(line) > MAX_LINE_LENGTH:
            ignored += 1
            continue
        header = _HEADER.fullmatch(line)
        month = _MONTHS.get(header["mon"]) if header else None
        if header is None or month is None:
            ignored += 1
            continue

        # El cambio de año se detecta con cualquier línea con cabecera, aunque se ignore después.
        if year is not None and previous_month is not None and month < previous_month:
            year += 1
        previous_month = month

        parsed = _parse_message(header["proc"], header["msg"])
        if parsed is None:
            ignored += 1
            continue

        if year is None:
            records.append(
                RawRecord(number, None, (RejectionCode.MISSING_TIME_CONTEXT, "timestamp"))
            )
            continue
        try:
            naive = datetime(
                year,
                month,
                int(header["day"]),
                int(header["hour"]),
                int(header["minute"]),
                int(header["second"]),
            )
        except ValueError:
            records.append(RawRecord(number, None, (RejectionCode.INVALID_TIMESTAMP, "timestamp")))
            continue
        utc = _to_utc(naive, tz)
        if utc is None:
            records.append(RawRecord(number, None, (RejectionCode.INVALID_TIMESTAMP, "timestamp")))
            continue

        records.append(
            RawRecord(
                number,
                {
                    "event_id": "la-" + pseudonymizer.derive_id("id", number, line),
                    "timestamp": utc.isoformat(),
                    "source": SOURCE,
                    "event_type": parsed.event_type,
                    "action": parsed.action,
                    "outcome": parsed.outcome,
                    "username": parsed.username,
                    "source_ip": parsed.source_ip,
                    "host": header["host"],
                },
            )
        )
    return records, ignored
