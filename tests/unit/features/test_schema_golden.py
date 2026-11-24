"""FR-003-18, 21 y SC-007: el par (versión, huella) del esquema está fijado.

Si este test falla, alguien ha cambiado el nombre, el orden, el tipo, el ámbito o la definición de
una característica (o la ventana). Eso invalida los modelos entrenados con el esquema anterior:
sube `FEATURE_SCHEMA_VERSION`, actualiza ambos valores de abajo y registra el cambio en un ADR.
"""

from security_anomaly.features.schema import FEATURE_SCHEMA, FEATURE_SCHEMA_VERSION

PINNED_VERSION = 1
PINNED_FINGERPRINT = "86ea5d4603646ab6343dd454520bb970568227f1c296d75d4448eea478e44c09"


def test_the_schema_version_and_fingerprint_are_pinned() -> None:
    assert (FEATURE_SCHEMA_VERSION, FEATURE_SCHEMA.fingerprint) == (
        PINNED_VERSION,
        PINNED_FINGERPRINT,
    ), (
        "El esquema de características ha cambiado: sube FEATURE_SCHEMA_VERSION, actualiza "
        "PINNED_VERSION y PINNED_FINGERPRINT y escribe un ADR."
    )


def test_the_fingerprint_is_stable_across_instances() -> None:
    from security_anomaly.schemas.features import FeatureSchema

    clone = FeatureSchema.model_validate(FEATURE_SCHEMA.model_dump())
    assert clone.fingerprint == FEATURE_SCHEMA.fingerprint
