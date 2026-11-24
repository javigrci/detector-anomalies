"""Esquema de características v1 (contracts/feature-schema.md).

Cambiar el nombre, el orden, el tipo, el ámbito o la definición de una característica, o la
ventana, cambia la huella: un test fija el par ``(versión, huella)`` y exige subir la versión.
"""

from datetime import timedelta

from security_anomaly.schemas.features import FeatureDefinition, FeatureSchema

FEATURE_SCHEMA_VERSION = 1
WINDOW = timedelta(minutes=5)

FEATURE_SCHEMA = FeatureSchema(
    version=FEATURE_SCHEMA_VERSION,
    window_seconds=int(WINDOW.total_seconds()),
    definitions=(
        FeatureDefinition(
            name="hour_sin",
            kind="float",
            scope="event",
            definition="sin(2*pi*h/24), h = hora entera UTC del evento, redondeado a 12 decimales",
        ),
        FeatureDefinition(
            name="hour_cos",
            kind="float",
            scope="event",
            definition="cos(2*pi*h/24), h = hora entera UTC del evento, redondeado a 12 decimales",
        ),
        FeatureDefinition(
            name="day_of_week",
            kind="int",
            scope="event",
            definition="dia de la semana UTC del evento, lunes = 0 hasta domingo = 6",
        ),
        FeatureDefinition(
            name="event_type",
            kind="category",
            scope="event",
            definition="tipo de evento del catalogo v1 del incremento 1",
        ),
        FeatureDefinition(
            name="action",
            kind="category",
            scope="event",
            definition="accion del catalogo v1 del incremento 1",
        ),
        FeatureDefinition(
            name="outcome",
            kind="category",
            scope="event",
            definition="resultado del catalogo v1 del incremento 1",
        ),
        FeatureDefinition(
            name="source",
            kind="category",
            scope="event",
            definition="fuente del evento",
        ),
        FeatureDefinition(
            name="ip_event_count",
            kind="int",
            scope="window",
            definition="eventos de (source, ip) en (t - 5 min, t], incluido el propio; 0 sin IP",
        ),
        FeatureDefinition(
            name="ip_failure_count",
            kind="int",
            scope="window",
            definition="eventos de (source, ip) con resultado failure en la ventana; 0 sin IP",
        ),
        FeatureDefinition(
            name="ip_failure_rate",
            kind="float",
            scope="window",
            definition="ip_failure_count / ip_event_count; 0 sin IP",
        ),
        FeatureDefinition(
            name="ip_distinct_users",
            kind="int",
            scope="window",
            definition="seudonimos distintos no nulos de (source, ip) en la ventana; 0 sin IP",
        ),
        FeatureDefinition(
            name="user_distinct_ips",
            kind="int",
            scope="window",
            definition="IPs distintas no nulas de (source, usuario) en la ventana; 0 sin usuario",
        ),
        FeatureDefinition(
            name="has_ip",
            kind="int",
            scope="indicator",
            definition="1 si el evento tiene IP, 0 si no",
        ),
        FeatureDefinition(
            name="has_user",
            kind="int",
            scope="indicator",
            definition="1 si el evento tiene usuario, 0 si no",
        ),
    ),
)
