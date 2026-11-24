"""Características causales por evento y por ventana de 5 minutos (incremento 3).

API pública: ver ``specs/003-feature-engineering/contracts/features-api.md``. Un único motor sirve
al entrenamiento (lotes y rangos) y a la inferencia (un evento con su historia previa).
"""

from security_anomaly.features.engine import EventLike
from security_anomaly.features.errors import FeatureError
from security_anomaly.features.pipeline import (
    compute_event_features,
    compute_features,
    features_for_range,
)
from security_anomaly.features.schema import FEATURE_SCHEMA, FEATURE_SCHEMA_VERSION
from security_anomaly.schemas.features import FeatureSchema, FeatureVector

__all__ = [
    "FEATURE_SCHEMA",
    "FEATURE_SCHEMA_VERSION",
    "EventLike",
    "FeatureError",
    "FeatureSchema",
    "FeatureVector",
    "compute_event_features",
    "compute_features",
    "features_for_range",
]
