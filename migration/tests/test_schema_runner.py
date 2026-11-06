"""Unit tests for the numbered SQL runner. No database connection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "db"))

from migrate import (  # noqa: E402
    Migration,
    MigrationError,
    apply_pending,
    discover,
    guard_schema,
    split_sql,
)


class FakeCursor:
    def __init__(self, recorded: list[dict] | None = None):
        self.recorded = list(recorded or [])
        self.statements: list[str] = []
        self.fail_on: str | None = None

    def execute(self, sql, args=None):
        text = " ".join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("statement failed")
        if text.startswith("SELECT version, checksum"):
            self._rows = list(self.recorded)
            return
        if text.startswith("INSERT INTO schema_migrations"):
            version, _name, checksum, _applied = args
            self.recorded.append({"version": version, "checksum": checksum})
            self._rows = []
            return
        self.statements.append(text)
        self._rows = []

    def fetchall(self):
        return list(getattr(self, "_rows", []))


def _migration(tmp_path: Path, version: int, slug: str, sql: str) -> None:
    (tmp_path / f"{version:04d}_{slug}.sql").write_text(sql, encoding="utf-8")


def test_guard_allows_test_and_refuses_prod_and_scissortail():
    guard_schema("f3ttown_test", allow_prod=False)
    guard_schema("f3ttown_rehearsal", allow_prod=False)
    with pytest.raises(MigrationError, match="allow-prod"):
        guard_schema("f3ttown_prod", allow_prod=False)
    guard_schema("f3ttown_prod", allow_prod=True)
    with pytest.raises(MigrationError, match="outside"):
        guard_schema("f3scissortail_test", allow_prod=False)
    with pytest.raises(MigrationError, match="outside"):
        guard_schema("weaselbot_test", allow_prod=False)
    with pytest.raises(MigrationError, match="must look like"):
        guard_schema("F3Town_test", allow_prod=False)


def test_discover_rejects_gaps_duplicates_and_bad_names(tmp_path: Path):
    _migration(tmp_path, 1, "alpha", "SELECT 1;")
    _migration(tmp_path, 3, "gamma", "SELECT 3;")
    with pytest.raises(MigrationError, match="gaps"):
        discover(tmp_path)

    (tmp_path / "0003_gamma.sql").unlink()
    _migration(tmp_path, 2, "beta", "SELECT 2;")
    found = discover(tmp_path)
    assert [m.version for m in found] == [1, 2]

    (tmp_path / "0002_other.sql").write_text("SELECT 9;", encoding="utf-8")
    with pytest.raises(MigrationError, match="duplicate"):
        discover(tmp_path)


def test_split_sql_ignores_semicolons_inside_strings_and_comments():
    text = """
    -- a comment with a ; semicolon
    SELECT 'a;b';
    /* block ; comment */
    SELECT "c;d";
    """
    assert split_sql(text) == ["SELECT 'a;b'", 'SELECT "c;d"']


def test_split_sql_keeps_executable_comments_and_quotes():
    tidb = (
        "CREATE TABLE t (id INT, PRIMARY KEY (id) "
        "/*T![clustered_index] NONCLUSTERED */);"
    )
    assert split_sql(tidb) == [
        "CREATE TABLE t (id INT, PRIMARY KEY (id) /*T![clustered_index] NONCLUSTERED */)"
    ]
    assert split_sql("/*!40101 SET NAMES utf8mb4 */;") == ["/*!40101 SET NAMES utf8mb4 */"]
    assert split_sql("SELECT 5--3;") == ["SELECT 5--3"]
    assert split_sql(r"SELECT 'it\'s; ok';") == [r"SELECT 'it\'s; ok'"]
    assert split_sql("SELECT 'it''s; ok';") == ["SELECT 'it''s; ok'"]
    assert split_sql("SELECT `a;b`;") == ["SELECT `a;b`"]
    hashed = split_sql("SELECT 1 # c;\n;")
    assert hashed == ["SELECT 1 # c;\n"]


def test_split_sql_skips_plain_comments_and_rejects_delimiter():
    assert split_sql("SELECT 1;\n-- only\n;\nSELECT 2;") == ["SELECT 1", "SELECT 2"]
    assert split_sql("SELECT 1; -- note") == ["SELECT 1"]
    body = "CREATE TABLE t (id INT /*!50100 PARTITION BY HASH(id) */);"
    assert split_sql(body) == ["CREATE TABLE t (id INT /*!50100 PARTITION BY HASH(id) */)"]
    assert split_sql("\ufeffSELECT 1;\r\nSELECT 2;") == ["SELECT 1", "SELECT 2"]
    with pytest.raises(MigrationError, match="DELIMITER"):
        split_sql("DELIMITER $$\nSELECT 1;\n")


def test_apply_records_only_after_success_and_stops_at_to():
    first = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT 1; SELECT 2;")
    second = Migration(2, "beta", Path("0002_beta.sql"), "def", "SELECT 3;")
    cursor = FakeCursor()
    applied = apply_pending(cursor, [first, second], to=1)
    assert applied == [1]
    assert cursor.statements == ["SELECT 1", "SELECT 2"]
    assert cursor.recorded[0]["version"] == 1

    again = apply_pending(cursor, [first, second], to=None)
    assert again == [2]


def test_apply_refuses_a_changed_checksum_and_skips_the_insert_on_failure():
    Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT 1;")
    cursor = FakeCursor([{"version": 1, "checksum": "abc"}])
    changed = Migration(1, "alpha", Path("0001_alpha.sql"), "zzz", "SELECT 9;")
    with pytest.raises(MigrationError, match="checksum"):
        apply_pending(cursor, [changed])

    fresh = FakeCursor()
    failing = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT ok; SELECT FAIL;")
    fresh.fail_on = "FAIL"
    with pytest.raises(MigrationError, match="failed on"):
        apply_pending(fresh, [failing])
    assert fresh.recorded == []
