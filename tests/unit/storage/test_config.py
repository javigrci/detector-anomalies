"""FR-002-15, FR-002-19, FR-002-22: configuración de la persistencia."""

import pytest
from pydantic import ValidationError

from security_anomaly.core.config import ConfigError
from security_anomaly.storage.config import (
    AdminSettings,
    MaintenanceSettings,
    MigrationSettings,
    StoragePolicy,
    load_admin_settings,
    load_maintenance_settings,
    load_migration_settings,
    load_storage_policy,
)

URL = "postgresql+psycopg://u:SENTINEL-PASSWORD-x@localhost:5432/db"
GOOD_PASSWORDS = {
    "MIGRATOR_DB_PASSWORD": "aaaaaaaaaaaa1",
    "APP_DB_PASSWORD": "bbbbbbbbbbbb2",
    "MAINT_DB_PASSWORD": "cccccccccccc3",
}


def test_policy_defaults() -> None:
    policy = StoragePolicy()
    assert (policy.retention_days, policy.query_default_limit, policy.query_max_limit) == (
        90,
        100,
        1000,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"retention_days": 0},
        {"retention_days": -1},
        {"query_default_limit": 0},
        {"query_max_limit": 0},
        {"query_default_limit": 2000, "query_max_limit": 1000},
    ],
)
def test_policy_rejects_invalid(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        StoragePolicy(**kwargs)


def test_policy_from_environment() -> None:
    policy = load_storage_policy(
        {"RETENTION_DAYS": "30", "QUERY_DEFAULT_LIMIT": "10", "QUERY_MAX_LIMIT": "50"}
    )
    assert (policy.retention_days, policy.query_default_limit, policy.query_max_limit) == (
        30,
        10,
        50,
    )


def test_policy_blank_values_are_absent() -> None:
    assert load_storage_policy({"RETENTION_DAYS": "  "}).retention_days == 90


def test_policy_invalid_names_variable_not_value() -> None:
    with pytest.raises(ConfigError) as exc:
        load_storage_policy({"RETENTION_DAYS": "-5"})
    assert "RETENTION_DAYS" in str(exc.value)
    assert "-5" not in str(exc.value)


def test_migration_and_maintenance_settings_read_their_own_variable() -> None:
    assert (
        load_migration_settings({"MIGRATION_DATABASE_URL": URL}).migration_database_url
    ).get_secret_value() == URL
    assert (
        load_maintenance_settings({"MAINTENANCE_DATABASE_URL": URL}).maintenance_database_url
    ).get_secret_value() == URL
    assert isinstance(load_migration_settings({"MIGRATION_DATABASE_URL": URL}), MigrationSettings)
    assert isinstance(
        load_maintenance_settings({"MAINTENANCE_DATABASE_URL": URL}), MaintenanceSettings
    )


def test_urls_are_not_cross_loaded() -> None:
    with pytest.raises(ConfigError) as exc:
        load_maintenance_settings({"MIGRATION_DATABASE_URL": URL})
    assert "MAINTENANCE_DATABASE_URL" in str(exc.value)


@pytest.mark.parametrize(
    "loader,var",
    [
        (load_migration_settings, "MIGRATION_DATABASE_URL"),
        (load_maintenance_settings, "MAINTENANCE_DATABASE_URL"),
    ],
)
def test_bad_scheme_is_rejected_without_value(loader, var) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ConfigError) as exc:
        loader({var: "mysql://u:SENTINEL-PASSWORD-x@h/db"})
    assert var in str(exc.value)
    assert "SENTINEL" not in str(exc.value)


def test_secrets_do_not_appear_in_repr() -> None:
    settings = load_migration_settings({"MIGRATION_DATABASE_URL": URL})
    assert "SENTINEL" not in repr(settings)
    assert "SENTINEL" not in str(settings)


def _admin(**overrides: str) -> dict[str, str]:
    return {"ADMIN_DATABASE_URL": URL, **GOOD_PASSWORDS, **overrides}


def test_admin_settings_valid() -> None:
    settings = load_admin_settings(_admin())
    assert isinstance(settings, AdminSettings)
    assert settings.app_db_password.get_secret_value() == "bbbbbbbbbbbb2"


@pytest.mark.parametrize(
    "var,value",
    [
        ("APP_DB_PASSWORD", "corta"),
        ("APP_DB_PASSWORD", "change-me-app-url-safe-password"),
        ("MAINT_DB_PASSWORD", "tiene@arroba12345"),
        ("MAINT_DB_PASSWORD", "tiene:dospuntos123"),
        ("MIGRATOR_DB_PASSWORD", "tiene/barra123456"),
        ("MIGRATOR_DB_PASSWORD", "tiene?interr12345"),
        ("MIGRATOR_DB_PASSWORD", "tiene#almoh123456"),
        ("MIGRATOR_DB_PASSWORD", "tiene%porc1234567"),
    ],
)
def test_admin_rejects_weak_or_unsafe_passwords(var: str, value: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_admin_settings(_admin(**{var: value}))
    assert var in str(exc.value)
    assert value not in str(exc.value)


def test_admin_rejects_repeated_passwords() -> None:
    with pytest.raises(ConfigError) as exc:
        load_admin_settings(_admin(APP_DB_PASSWORD=GOOD_PASSWORDS["MAINT_DB_PASSWORD"]))
    assert GOOD_PASSWORDS["MAINT_DB_PASSWORD"] not in str(exc.value)


def test_admin_missing_variable_is_named() -> None:
    env = _admin()
    del env["APP_DB_PASSWORD"]
    with pytest.raises(ConfigError) as exc:
        load_admin_settings(env)
    assert "APP_DB_PASSWORD" in str(exc.value)


def test_admin_settings_repr_hides_passwords() -> None:
    settings = load_admin_settings(_admin())
    assert "aaaaaaaaaaaa1" not in repr(settings)
    assert "SENTINEL" not in repr(settings)
