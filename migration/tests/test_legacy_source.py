"""A missing source schema is an error, not a successful empty import."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "migration"))

from legacy_import import _require_present  # noqa: E402
from migrate import MigrationError  # noqa: E402


class ScriptedCursor:
    def __init__(self, fetches):
        self.fetches = list(fetches)

    def execute(self, sql, params=()):
        return None

    def fetchone(self):
        if not self.fetches:
            return None
        return self.fetches.pop(0)

    def fetchall(self):
        return []


def test_missing_source_schema_is_refused():
    cursor = ScriptedCursor([None])
    with pytest.raises(MigrationError, match="does not exist"):
        _require_present(cursor, "missing_prod", ("users",))


def test_missing_source_table_is_refused():
    cursor = ScriptedCursor([{"name": "old_prod"}])
    with pytest.raises(MigrationError, match="missing users"):
        _require_present(cursor, "old_prod", ("users",))
