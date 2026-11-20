"""Ingesta y normalización de logs de auditoría (SPEC §4).

Biblioteca sin interfaz: los incrementos posteriores la consumen como funciones. La API pública y
sus garantías están en ``specs/001-ingestion/contracts/ingestion-api.md``.
"""

from security_anomaly.core.config import ConfigError
from security_anomaly.ingestion.errors import BatchRejected, IngestionError, PseudonymKeyMissing
from security_anomaly.ingestion.pipeline import ingest_file, ingest_linux_auth, ingest_records
from security_anomaly.ingestion.policy import IngestionPolicy
from security_anomaly.ingestion.pseudonym import Pseudonymizer
from security_anomaly.ingestion.synthetic import (
    SyntheticConfig,
    SyntheticDataset,
    SyntheticLabel,
    generate_synthetic,
)
from security_anomaly.schemas.event import NormalizedEvent
from security_anomaly.schemas.ingestion import (
    BatchRejectionCode,
    IngestionReport,
    IngestionResult,
    Rejection,
    RejectionCode,
)

__all__ = [
    "BatchRejected",
    "BatchRejectionCode",
    "ConfigError",
    "IngestionError",
    "IngestionPolicy",
    "IngestionReport",
    "IngestionResult",
    "NormalizedEvent",
    "PseudonymKeyMissing",
    "Pseudonymizer",
    "Rejection",
    "RejectionCode",
    "SyntheticConfig",
    "SyntheticDataset",
    "SyntheticLabel",
    "generate_synthetic",
    "ingest_file",
    "ingest_linux_auth",
    "ingest_records",
]
