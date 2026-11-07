"""Guards for the test-only schema copy. No database connection."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "migration"))
sys.path.insert(0, str(_REPO / "db"))

from copy_into_region import (  # noqa: E402
    REGION_CONFIG_DDL,
    TARGET,
    TEST,
    copy_bolt,
    copy_region_config,
    copy_table,
    guard,
)
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


def test_guard_allows_prod_only_with_the_flag(tmp_path: Path):
    path = tmp_path / ".env.migration.prod"
    path.write_text(
        "F3_REGION_NAME=f3ttown\nTARGET_HOST=h\nTARGET_USER=u\nTARGET_PASSWORD=p\n",
        encoding="utf-8",
    )
    with pytest.raises(MigrationError, match="refusing stage"):
        guard(path)
    dest, _settings = guard(path, allow_prod=True)
    assert dest.target == "f3ttown_prod"


def test_guard_refuses_a_prod_env_file(tmp_path: Path):
    path = tmp_path / ".env.migration.prod"
    path.write_text("F3_REGION_NAME=f3ttown\nTARGET_HOST=h\nTARGET_USER=u\nTARGET_PASSWORD=p\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="refusing stage"):
        guard(path)


class FakeCursor:
    def __init__(self, tables, counts, region_counts=None, columns=None, schema_name=TARGET):
        self.tables = set(tables)
        self.counts = dict(counts)
        self.region_counts = region_counts or {}
        self.columns = columns or {}
        self.schema_name = schema_name
        self.executed = []
        self.rowcount = 1
        self._one = None
        self._many = []

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if "schema_name AS name" in sql:
            self._one = {"name": self.schema_name}
        elif "information_schema.TABLES" in sql:
            schema, table = params
            self._one = {"name": table} if (schema, table) in self.tables else None
        elif "information_schema.COLUMNS" in sql:
            schema, table = params
            self._many = [{"name": name} for name in self.columns.get((schema, table), [])]
        elif "COUNT(*)" in sql and "WHERE" in sql:
            self._one = {"c": self.region_counts.get(params, 0)}
        elif "COUNT(*)" in sql:
            match = re.search(r"FROM `([^`]+)`.`([^`]+)`", sql)
            self._one = {"c": self.counts.get((match.group(1), match.group(2)), 0)}
        elif "CREATE TABLE IF NOT EXISTS" in sql and "region_config" in sql:
            self.tables.add((TARGET, "region_config"))
            self.counts[(TARGET, "region_config")] = 0
        else:
            self._one = None

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


def test_copy_table_refuses_a_count_mismatch():
    cursor = FakeCursor(
        tables={(TARGET, "qsignups_master"), ("qsignups_test", "qsignups_master")},
        counts={(TARGET, "qsignups_master"): 1, ("qsignups_test", "qsignups_master"): 2},
    )
    with pytest.raises(MigrationError, match="drop it in f3ttown_test"):
        copy_table(cursor, "qsignups_test", "qsignups_master", dest=TEST, yes=False)


def test_second_run_does_not_insert_oauth_states():
    cursor = FakeCursor(
        tables={
            (TARGET, "slack_oauth_states"),
            ("slackblast_test", "slack_oauth_states"),
            ("qsignups_test", "slack_oauth_states"),
        },
        counts={
            (TARGET, "slack_oauth_states"): 1,
            ("slackblast_test", "slack_oauth_states"): 1,
            ("qsignups_test", "slack_oauth_states"): 2,
        },
        columns={("qsignups_test", "slack_oauth_states"): ["id", "state"]},
    )
    copy_bolt(cursor, "slack_oauth_states", dest=TEST, yes=True)
    assert not any(sql.strip().upper().startswith("INSERT") for sql in cursor.executed)


def test_region_config_refuses_the_wrong_number_of_source_rows():
    cursor = FakeCursor(tables=set(), counts={}, region_counts={("f3ttown",): 1, (TARGET,): 0})
    with pytest.raises(MigrationError, match="expected 1 row, found 0"):
        copy_region_config(cursor, dest=TEST, yes=False)
    cursor.region_counts[(TARGET,)] = 2
    with pytest.raises(MigrationError, match="expected 1 row, found 2"):
        copy_region_config(cursor, dest=TEST, yes=False)


def test_region_config_is_created_when_missing():
    cursor = FakeCursor(tables=set(), counts={}, region_counts={("f3ttown",): 1, (TARGET,): 1})
    note = copy_region_config(cursor, dest=TEST, yes=True)
    assert "create region_config" in note
    assert any("CREATE TABLE IF NOT EXISTS" in sql and f"`{TARGET}`.`region_config`" in sql for sql in cursor.executed)


def test_region_config_refuses_a_prod_schema_pointer():
    cursor = FakeCursor(
        tables=set(),
        counts={},
        region_counts={("f3ttown",): 1, (TARGET,): 1},
        schema_name="f3ttown_prod",
    )
    with pytest.raises(MigrationError, match="schema_name"):
        copy_region_config(cursor, dest=TEST, yes=False)


def test_region_config_refuses_an_insert_that_changes_no_rows():
    cursor = FakeCursor(tables=set(), counts={}, region_counts={("f3ttown",): 1, (TARGET,): 1})
    cursor.rowcount = 0
    with pytest.raises(MigrationError, match="changed 0 rows"):
        copy_region_config(cursor, dest=TEST, yes=True)


def test_guard_accepts_the_rehearsal_file(tmp_path: Path):
    path = tmp_path / ".env.migration.rehearsal"
    path.write_text(
        "F3_REGION_NAME=f3ttown\nTARGET_HOST=h\nTARGET_USER=u\nTARGET_PASSWORD=p\n",
        encoding="utf-8",
    )
    dest, _settings = guard(path)
    assert dest.target == "f3ttown_rehearsal"
    assert dest.paxminer == "paxminer_rehearsal"
    assert dest.qsignups == "qsignups_rehearsal"


def test_guard_refuses_any_schema_but_f3ttown_test(tmp_path: Path):
    path = tmp_path / ".env.migration.test"
    path.write_text(
        "F3_REGION_NAME=other\nTARGET_HOST=h\nTARGET_USER=u\nTARGET_PASSWORD=p\n",
        encoding="utf-8",
    )
    with pytest.raises(MigrationError, match="f3ttown_test"):
        guard(path)
