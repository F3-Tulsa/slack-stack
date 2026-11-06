"""Guards for the test-only schema copy. No database connection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "db"))

from copy_into_region import guard  # noqa: E402
from migrate import MigrationError  # noqa: E402


def test_guard_refuses_a_prod_env_file(tmp_path: Path):
    path = tmp_path / ".env.migration.prod"
    path.write_text("F3_REGION_NAME=f3ttown\nTARGET_HOST=h\nTARGET_USER=u\nTARGET_PASSWORD=p\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="not a test"):
        guard(path)


def test_guard_refuses_any_schema_but_f3ttown_test(tmp_path: Path):
    path = tmp_path / ".env.migration.test"
    path.write_text(
        "F3_REGION_NAME=other\nTARGET_HOST=h\nTARGET_USER=u\nTARGET_PASSWORD=p\n",
        encoding="utf-8",
    )
    with pytest.raises(MigrationError, match="f3ttown_test"):
        guard(path)
