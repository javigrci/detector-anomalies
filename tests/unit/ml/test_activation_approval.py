"""FR-004-26: la aprobación se exige antes de tocar la base de datos."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from security_anomaly.ml.config import MlSettings
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.registry import activate_version


@pytest.mark.parametrize("approved", [False, None, "yes", 1, 0, "true"])
def test_no_approval_means_no_database_access(tmp_path: Path, approved: object) -> None:
    engine = MagicMock()
    with pytest.raises(MlError) as caught:
        activate_version(engine, MlSettings(model_dir=tmp_path), "v0001", approved=approved)  # type: ignore[arg-type]
    assert caught.value.code == "approval_required"
    engine.connect.assert_not_called()
    engine.begin.assert_not_called()
    assert "v0001" not in f"{caught.value!s} {caught.value!r}"
