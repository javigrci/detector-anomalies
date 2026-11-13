"""Configuración por variables de entorno (FR-000-03).

Los errores de validación nombran la variable y el tipo de error, nunca su valor.
"""

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

ENV_VARS: dict[str, str] = {
    "app_env": "APP_ENV",
    "log_level": "LOG_LEVEL",
    "database_url": "DATABASE_URL",
    "db_connect_timeout_s": "DB_CONNECT_TIMEOUT_S",
    "api_port": "API_PORT",
}
_DATABASE_SCHEME = "postgresql+psycopg://"


class ConfigError(Exception):
    """Configuración inválida; el mensaje no contiene valores de las variables."""


class Settings(BaseModel):
    """Ajustes del servicio; se validan una sola vez al arrancar."""

    model_config = ConfigDict(frozen=True)

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: SecretStr
    db_connect_timeout_s: int = Field(default=2, ge=1, le=30)
    api_port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("database_url")
    @classmethod
    def _check_scheme(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(_DATABASE_SCHEME):
            raise ValueError("esquema no soportado")
        return value


def _describe(error_type: str) -> str:
    return "obligatoria" if error_type == "missing" else f"valor inválido ({error_type})"


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Carga y valida los ajustes. Los valores vacíos se tratan como ausentes."""
    source = os.environ if environ is None else environ
    raw: dict[str, str] = {}
    for field, name in ENV_VARS.items():
        value = source.get(name)
        if value is not None and value.strip():
            raw[field] = value.strip()
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_input=False, include_url=False):
            field = str(error["loc"][0]) if error["loc"] else "?"
            problems.append(f"{ENV_VARS.get(field, field)}: {_describe(error['type'])}")
        raise ConfigError("Configuración inválida: " + "; ".join(problems)) from None
