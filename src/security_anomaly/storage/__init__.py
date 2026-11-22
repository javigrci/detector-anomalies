"""Persistencia de eventos en PostgreSQL (incremento 2).

API pública: ver ``specs/002-persistence/contracts/storage-api.md``. Cada función recibe un
``Engine`` ya creado con el rol que le corresponde; la API nunca guarda credenciales.
"""

from security_anomaly.core.config import ConfigError
from security_anomaly.schemas.storage import (
    EventFilter,
    EventPage,
    PurgeResult,
    SaveSummary,
    StoredEvent,
)
from security_anomaly.storage.config import StoragePolicy
from security_anomaly.storage.errors import StorageError
from security_anomaly.storage.events import query_events, read_range, save_events
from security_anomaly.storage.retention import purge_events
from security_anomaly.storage.roles import RolePasswords, provision_roles

__all__ = [
    "ConfigError",
    "EventFilter",
    "EventPage",
    "PurgeResult",
    "RolePasswords",
    "SaveSummary",
    "StorageError",
    "StoragePolicy",
    "StoredEvent",
    "provision_roles",
    "purge_events",
    "query_events",
    "read_range",
    "save_events",
]
