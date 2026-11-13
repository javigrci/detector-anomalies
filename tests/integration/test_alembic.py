"""FR-000-19: las migraciones están conectadas y no crean tablas de negocio."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def test_upgrade_head_succeeds_without_business_tables() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail("Los tests de integración requieren DATABASE_URL", pytrace=False)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables <= {"alembic_version"}
