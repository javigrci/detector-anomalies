"""research R11: carga de configuración reutilizable con errores sin valores."""

from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from security_anomaly.core.config import ConfigError, load_model


class _Demo(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    mode: Literal["fast", "slow"] = "fast"
    port: int = Field(default=80, ge=1, le=65535)
    secret: SecretStr | None = None


ENV = {"name": "DEMO_NAME", "mode": "DEMO_MODE", "port": "DEMO_PORT", "secret": "DEMO_SECRET"}


def test_loads_values_and_defaults() -> None:
    model = load_model(_Demo, ENV, {"DEMO_NAME": "x", "DEMO_PORT": "8080"})
    assert model.name == "x"
    assert model.mode == "fast"
    assert model.port == 8080
    assert model.secret is None


def test_blank_values_count_as_absent() -> None:
    model = load_model(_Demo, ENV, {"DEMO_NAME": "ok", "DEMO_PORT": "   ", "DEMO_MODE": ""})
    assert model.port == 80
    assert model.mode == "fast"


def test_missing_required_names_the_variable() -> None:
    with pytest.raises(ConfigError) as exc:
        load_model(_Demo, ENV, {})
    assert "DEMO_NAME" in str(exc.value)
    assert "obligatoria" in str(exc.value)


@pytest.mark.parametrize(
    ("variable", "value"),
    [("DEMO_MODE", "ludicrous-secret"), ("DEMO_PORT", "not-a-number-secret"), ("DEMO_PORT", "0")],
)
def test_invalid_values_name_the_variable_never_the_value(variable: str, value: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_model(_Demo, ENV, {"DEMO_NAME": "x", variable: value})
    message = str(exc.value)
    assert variable in message
    if len(value) > 3:
        assert value not in message


def test_secret_value_is_not_exposed_in_repr() -> None:
    model = load_model(_Demo, ENV, {"DEMO_NAME": "x", "DEMO_SECRET": "super-secret-value"})
    assert "super-secret-value" not in repr(model)
    assert model.secret is not None
    assert model.secret.get_secret_value() == "super-secret-value"
