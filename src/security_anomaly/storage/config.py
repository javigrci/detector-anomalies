"""Configuración de la persistencia (FR-002-15, FR-002-19, FR-002-22; research R9).

Cada operación carga solo las credenciales que necesita: la API nunca ve las de mantenimiento ni
las del administrador. Los errores nombran la variable y nunca su valor.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from security_anomaly.core.config import load_model

_DATABASE_SCHEME = "postgresql+psycopg://"
_PLACEHOLDER = "change-me"
_MIN_PASSWORD_LENGTH = 12
_URL_RESERVED = set("@:/?#%")


def _check_url(value: SecretStr) -> SecretStr:
    if not value.get_secret_value().startswith(_DATABASE_SCHEME):
        raise ValueError("esquema no soportado")
    return value


def _check_password(value: SecretStr) -> SecretStr:
    raw = value.get_secret_value()
    if len(raw) < _MIN_PASSWORD_LENGTH:
        raise ValueError("contraseña demasiado corta")
    if _PLACEHOLDER in raw.lower():
        raise ValueError("marcador de ejemplo del repositorio")
    if any(ch in _URL_RESERVED or ch.isspace() for ch in raw):
        raise ValueError("caracteres no aptos para una URL")
    return value


class StoragePolicy(BaseModel):
    """Retención y paginación (decisión D8; SPEC §6.2)."""

    model_config = ConfigDict(frozen=True)

    retention_days: int = Field(default=90, ge=1)
    query_default_limit: int = Field(default=100, ge=1)
    query_max_limit: int = Field(default=1000, ge=1)

    @model_validator(mode="after")
    def _default_within_max(self) -> "StoragePolicy":
        if self.query_default_limit > self.query_max_limit:
            raise ValueError("el tamaño por defecto supera el máximo")
        return self


class MigrationSettings(BaseModel):
    """Credenciales del rol propietario del esquema (solo Alembic)."""

    model_config = ConfigDict(frozen=True)

    migration_database_url: SecretStr

    _url = field_validator("migration_database_url")(_check_url)


class MaintenanceSettings(BaseModel):
    """Credenciales del rol de mantenimiento (solo la purga)."""

    model_config = ConfigDict(frozen=True)

    maintenance_database_url: SecretStr

    _url = field_validator("maintenance_database_url")(_check_url)


class AdminSettings(BaseModel):
    """Administrador de PostgreSQL y contraseñas de los tres roles (solo el aprovisionamiento)."""

    model_config = ConfigDict(frozen=True)

    admin_database_url: SecretStr
    migrator_db_password: SecretStr
    app_db_password: SecretStr
    maint_db_password: SecretStr

    _url = field_validator("admin_database_url")(_check_url)
    _passwords = field_validator("migrator_db_password", "app_db_password", "maint_db_password")(
        _check_password
    )

    @model_validator(mode="after")
    def _distinct_passwords(self) -> "AdminSettings":
        values = {
            self.migrator_db_password.get_secret_value(),
            self.app_db_password.get_secret_value(),
            self.maint_db_password.get_secret_value(),
        }
        if len(values) != 3:
            raise ValueError("las contraseñas de los roles deben ser distintas")
        return self


STORAGE_POLICY_ENV = {
    "retention_days": "RETENTION_DAYS",
    "query_default_limit": "QUERY_DEFAULT_LIMIT",
    "query_max_limit": "QUERY_MAX_LIMIT",
}
MIGRATION_ENV = {"migration_database_url": "MIGRATION_DATABASE_URL"}
MAINTENANCE_ENV = {"maintenance_database_url": "MAINTENANCE_DATABASE_URL"}
ADMIN_ENV = {
    "admin_database_url": "ADMIN_DATABASE_URL",
    "migrator_db_password": "MIGRATOR_DB_PASSWORD",
    "app_db_password": "APP_DB_PASSWORD",
    "maint_db_password": "MAINT_DB_PASSWORD",
}


def load_storage_policy(environ: Mapping[str, str] | None = None) -> StoragePolicy:
    return load_model(StoragePolicy, STORAGE_POLICY_ENV, environ)


def load_migration_settings(environ: Mapping[str, str] | None = None) -> MigrationSettings:
    return load_model(MigrationSettings, MIGRATION_ENV, environ)


def load_maintenance_settings(environ: Mapping[str, str] | None = None) -> MaintenanceSettings:
    return load_model(MaintenanceSettings, MAINTENANCE_ENV, environ)


def load_admin_settings(environ: Mapping[str, str] | None = None) -> AdminSettings:
    return load_model(AdminSettings, ADMIN_ENV, environ)
