"""FR-004-31: errores controlados del entrenamiento, sin valores de datos, rutas ni credenciales."""

import pytest

from security_anomaly.ml.errors import MlError

CODES = [
    "insufficient_data",
    "invalid_schema",
    "invalid_parameters",
    "training_in_progress",
    "training_failed",
    "unknown_version",
    "unknown_run",
    "approval_required",
    "no_active_model",
    "artifact_path",
    "artifact_integrity",
    "incompatible_environment",
    "incompatible_features",
]


@pytest.mark.parametrize("code", CODES)
def test_each_code_has_a_fixed_message(code: str) -> None:
    error = MlError(code)  # type: ignore[arg-type]
    assert error.code == code
    assert str(error) and str(error) == str(MlError(code))


def test_messages_are_distinct_per_code() -> None:
    assert len({str(MlError(c)) for c in CODES}) == len(CODES)  # type: ignore[arg-type]


@pytest.mark.parametrize("code", CODES)
def test_no_data_paths_or_credentials_in_text_repr_or_args(code: str) -> None:
    error = MlError(code)  # type: ignore[arg-type]
    for text in (str(error), repr(error), repr(error.args)):
        for forbidden in ("SENTINEL", "192.0.2", "usr_", "srv-demo", "/home", "postgresql", "/var"):
            assert forbidden not in text


def test_it_can_be_raised_and_caught() -> None:
    with pytest.raises(MlError) as caught:
        raise MlError("approval_required")
    assert caught.value.code == "approval_required"
