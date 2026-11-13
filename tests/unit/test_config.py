"""FR-000-03: configuración por entorno, validada y sin filtrar valores secretos."""

import pytest

from security_anomaly.core.config import ConfigError, load_settings

VALID = {"DATABASE_URL": "postgresql+psycopg://user:p4ssw0rd@localhost:5432/db"}


def test_defaults_are_applied() -> None:
    settings = load_settings(VALID)
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.db_connect_timeout_s == 2
    assert settings.api_port == 8000


def test_database_url_is_required() -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings({})
    assert "DATABASE_URL" in str(exc.value)


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_database_url_counts_as_missing(blank: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings({"DATABASE_URL": blank})
    assert "DATABASE_URL" in str(exc.value)


def test_blank_optional_variable_uses_default() -> None:
    settings = load_settings({**VALID, "API_PORT": "  ", "LOG_LEVEL": ""})
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("APP_ENV", "staging-secret"),
        ("LOG_LEVEL", "LOUD-secret"),
        ("API_PORT", "0"),
        ("API_PORT", "70000"),
        ("API_PORT", "not-a-port"),
        ("DB_CONNECT_TIMEOUT_S", "0"),
        ("DB_CONNECT_TIMEOUT_S", "31"),
        ("DB_CONNECT_TIMEOUT_S", "slow"),
    ],
)
def test_invalid_values_name_the_variable_not_the_value(name: str, value: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings({**VALID, name: value})
    message = str(exc.value)
    assert name in message
    if len(value) > 3:
        assert value not in message


def test_database_url_must_use_psycopg_scheme_and_never_leaks() -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings({"DATABASE_URL": "mysql://user:topsecretvalue@host/db"})
    message = str(exc.value)
    assert "DATABASE_URL" in message
    assert "topsecretvalue" not in message


def test_log_level_is_case_insensitive() -> None:
    assert load_settings({**VALID, "LOG_LEVEL": "debug"}).log_level == "DEBUG"


def test_secret_is_hidden_from_repr_and_str() -> None:
    settings = load_settings(VALID)
    assert "p4ssw0rd" not in repr(settings)
    assert "p4ssw0rd" not in str(settings)
    assert settings.database_url.get_secret_value() == VALID["DATABASE_URL"]
