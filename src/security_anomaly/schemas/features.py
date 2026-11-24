"""Modelos de las características: definición, esquema versionado y vector (data-model.md)."""

import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from security_anomaly.schemas.storage import UtcDatetime

FeatureKind = Literal["float", "int", "category"]
FeatureScope = Literal["event", "window", "indicator"]
FeatureValue = float | int | str


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class FeatureDefinition(_Model):
    """Una característica: su nombre, tipo, ámbito y el texto que fija su significado."""

    name: str = Field(min_length=1)
    kind: FeatureKind
    scope: FeatureScope
    definition: str = Field(min_length=1)


class FeatureSchema(_Model):
    """Esquema ordenado y versionado; su huella identifica el contenido exacto."""

    version: int = Field(ge=1)
    window_seconds: int = Field(ge=1)
    definitions: tuple[FeatureDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_names(self) -> "FeatureSchema":
        names = [d.name for d in self.definitions]
        if len(set(names)) != len(names):
            raise ValueError("los nombres de las características deben ser únicos")
        return self

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.definitions)

    @property
    def fingerprint(self) -> str:
        """SHA-256 del JSON canónico de versión, ventana y definiciones (research R1)."""
        canonical = json.dumps(
            {
                "version": self.version,
                "window_seconds": self.window_seconds,
                "definitions": [d.model_dump() for d in self.definitions],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FeatureVector(_Model):
    """Resultado de un evento. ``features`` solo lleva agregados, indicadores y categorías."""

    source: str
    event_id: str
    timestamp: UtcDatetime
    schema_version: int = Field(ge=1)
    context_complete: bool
    features: Mapping[str, FeatureValue]

    @field_validator("features")
    @classmethod
    def _read_only(cls, value: Mapping[str, FeatureValue]) -> Mapping[str, FeatureValue]:
        return MappingProxyType(dict(value))

    @field_serializer("features")
    def _serialize_features(self, value: Mapping[str, FeatureValue]) -> dict[str, FeatureValue]:
        return dict(value)
