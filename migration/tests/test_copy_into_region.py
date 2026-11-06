"""Guards for the test-only schema copy. No database connection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "db"))

from copy_into_region import REGION_CONFIG_DDL, guard  # noqa: E402
from migrate import MigrationError  # noqa: E402


def _not_null_without_default(ddl: str) -> list[str]:
    body = ddl.split("(", 1)[1].rsplit(")", 1)[0]
    required = []
    for raw in body.splitlines():
        line = raw.strip().rstrip(",")
        if not line or line.upper().startswith("PRIMARY"):
            continue
        upper = line.upper()
        if "NOT NULL" in upper and "DEFAULT" not in upper:
            required.append(line.split()[0].strip("`"))
    return required


def test_bootstrap_insert_covers_required_region_config_columns():
    """A cold-start insert must supply every NOT NULL column that has no default."""
    bootstrap = (_REPO / "PAXminer" / "common" / "token_bootstrap.py").read_text(encoding="utf-8")
    insert = bootstrap.split("INSERT INTO", 1)[1].split("VALUES", 1)[0]
    missing = [name for name in _not_null_without_default(REGION_CONFIG_DDL) if f"`{name}`" not in insert]
    assert missing == []


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
