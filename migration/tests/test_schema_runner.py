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
    connection_settings,
    derived_schema,
    discover,
    load_invocation,
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


def _args(**kwargs):
    defaults = {
        "env_file": None,
        "prefix": "DATABASE",
        "from_environment": False,
        "stage": None,
        "schema": None,
        "allow_prod": False,
        "migrations": Path("db/migrations"),
        "to": None,
    }
    defaults.update(kwargs)
    return type("Args", (), defaults)()


def _deploy_file(path: Path, stage: str, **extra: str) -> Path:
    body = {
        "F3_REGION_NAME": "f3ttown",
        "DATABASE_HOST": "from-file.example",
        "DATABASE_PORT": "4000",
        "DATABASE_USER": "user",
        "DATABASE_PASSWORD": "secret",
        "DATABASE_TLS_ENABLED": "true",
    }
    body.update(extra)
    path.write_text("".join(f"{key}={value}\n" for key, value in body.items()), encoding="utf-8")
    return path


def test_region_name_rules():
    assert derived_schema("f3ttown", "test") == "f3ttown_test"
    with pytest.raises(MigrationError, match="F3_REGION_NAME"):
        derived_schema("lake_wylie", "test")
    with pytest.raises(MigrationError, match="F3_REGION_NAME"):
        derived_schema("F3Town", "test")
    with pytest.raises(MigrationError, match="app schema"):
        derived_schema("paxminer", "test")
    with pytest.raises(MigrationError, match="F3_REGION_NAME"):
        derived_schema("", "test")


def test_prod_file_refuses_before_connect(tmp_path, monkeypatch):
    env_file = _deploy_file(tmp_path / ".env.deploy.prod", "prod")
    calls = []
    monkeypatch.setattr("migrate.connect", lambda settings: calls.append(settings))
    with pytest.raises(MigrationError, match="allow-prod"):
        load_invocation(_args(env_file=env_file))
    assert calls == []


def test_env_file_overrides_exported_host(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "from-env.example")
    env_file = _deploy_file(tmp_path / ".env.deploy.test", "test")
    schema, settings = load_invocation(_args(env_file=env_file))
    assert schema == "f3ttown_test"
    assert settings["host"] == "from-file.example"


def test_missing_env_file_does_not_use_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "from-env.example")
    monkeypatch.setenv("DATABASE_USER", "user")
    monkeypatch.setenv("DATABASE_PASSWORD", "secret")
    with pytest.raises(MigrationError, match="missing env file"):
        load_invocation(_args(env_file=tmp_path / ".env.deploy.test"))


def test_connection_fields_are_not_borrowed_across_prefixes():
    env = {"DATABASE_HOST": "db.example", "TARGET_PASSWORD": "secret"}
    with pytest.raises(MigrationError, match="DATABASE_USER"):
        connection_settings(env, "DATABASE")


def test_from_environment_stage_must_match(monkeypatch):
    monkeypatch.setenv("STAGE", "prod")
    monkeypatch.setenv("F3_REGION_NAME", "f3ttown")
    monkeypatch.setenv("DATABASE_HOST", "db.example")
    monkeypatch.setenv("DATABASE_USER", "user")
    monkeypatch.setenv("DATABASE_PASSWORD", "secret")
    with pytest.raises(MigrationError, match="STAGE"):
        load_invocation(_args(from_environment=True, stage="test"))


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
