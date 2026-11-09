"""Fresh install refuses Tulsa and does not store a bot token."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "db"))

from fresh_install import fresh_install, seed_qsignups_region, seed_region_config  # noqa: E402
from migrate import MigrationError  # noqa: E402


class ScriptedCursor:
    def __init__(self, fetches):
        self.fetches = list(fetches)
        self.sqls = []

    def execute(self, sql, params=()):
        self.sqls.append((sql, params))

    def fetchone(self):
        if not self.fetches:
            return None
        return self.fetches.pop(0)


def test_region_config_inserts_flag_defaults_and_an_empty_token():
    cursor = ScriptedCursor([None])
    assert seed_region_config(cursor, "newregion_test", region="newregion", team_id="T1", timezone="America/Chicago") == "inserted"
    sql, params = cursor.sqls[-1]
    assert params == ("newregion", "newregion_test", "America/Chicago", "T1")
    assert "1, '', %s, %s, 0, 0, 0, 0, 1, 1, 'ao_channel', 0" in sql
    assert "xox" not in sql


def test_qsignups_region_row_has_no_token():
    cursor = ScriptedCursor([None])
    assert seed_qsignups_region(cursor, team_id="T1", timezone="America/Chicago") == "inserted"
    sql, params = cursor.sqls[-1]
    assert "bot_token" not in sql
    assert params == ("T1", "America/Chicago")


def test_fresh_install_refuses_tulsa(monkeypatch):
    monkeypatch.setattr("fresh_install.run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("ran")))
    with pytest.raises(MigrationError, match="does not run on Tulsa"):
        fresh_install(
            Path("db/migrations"),
            "f3ttown_prod",
            {},
            region="f3ttown",
            team_id="T1",
            timezone="America/Chicago",
            to=None,
        )
