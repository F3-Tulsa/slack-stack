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
    created_names,
    derived_schema,
    discover,
    load_invocation,
    main,
    mark_applied,
    run,
    plan_history,
    split_sql,
)


class FakeCursor:
    def __init__(self, recorded: list[dict] | None = None, present: set[str] | None = None):
        self.recorded = list(recorded or [])
        self.present = set(present or [])
        self.other_tables = 0
        self.statements: list[str] = []
        self.fail_on: str | None = None

    def execute(self, sql, args=None):
        text = " ".join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("statement failed")
        if "information_schema.TABLES" in text and "COUNT(*)" in text:
            self._rows = [{"c": self.other_tables}]
            return
        if "information_schema.TABLES" in text:
            name = args[1]
            self._rows = [{"name": name}] if name in self.present else []
            return
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

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None


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


def test_port_and_tls_values_are_checked():
    env = {
        "DATABASE_HOST": "db.example",
        "DATABASE_USER": "user",
        "DATABASE_PASSWORD": "secret",
        "DATABASE_PORT": "40o0",
    }
    with pytest.raises(MigrationError, match="DATABASE_PORT"):
        connection_settings(env, "DATABASE")
    env["DATABASE_PORT"] = "4000"
    env["DATABASE_TLS_ENABLED"] = "ture"
    with pytest.raises(MigrationError, match="DATABASE_TLS_ENABLED"):
        connection_settings(env, "DATABASE")
    env["DATABASE_TLS_ENABLED"] = "false"
    assert connection_settings(env, "DATABASE")["tls"] is False
    del env["DATABASE_TLS_ENABLED"]
    assert connection_settings(env, "DATABASE")["tls"] is True


def test_missing_pymysql_does_not_hide_a_config_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pymysql", None)
    code = main(["--env-file", str(tmp_path / ".env.deploy.test")])
    captured = capsys.readouterr()
    assert code == 1
    assert "missing env file" in captured.err


def test_connection_fields_are_not_borrowed_across_prefixes():
    env = {"DATABASE_HOST": "db.example", "TARGET_PASSWORD": "secret"}
    with pytest.raises(MigrationError, match="DATABASE_USER"):
        connection_settings(env, "DATABASE")


def test_main_reports_connection_errors(tmp_path, monkeypatch, capsys):
    import pymysql

    env_file = _deploy_file(tmp_path / ".env.deploy.test", "test")
    migrations = tmp_path / "migrations"
    migrations.mkdir()

    def boom(_settings):
        raise pymysql.err.OperationalError(2003, "Can't connect")

    monkeypatch.setattr("migrate.connect", boom)
    code = main(
        ["--env-file", str(env_file), "--migrations", str(migrations)]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("error:")
    assert "secret" not in captured.err


def test_mark_applied_missing_schema_is_a_runner_error(tmp_path, monkeypatch, capsys):
    import pymysql

    env_file = _deploy_file(tmp_path / ".env.deploy.test", "test")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_alpha.sql").write_text("CREATE TABLE users (id INT);\n", encoding="utf-8")

    class Cursor:
        def execute(self, sql, args=None):
            if str(sql).startswith("USE"):
                raise pymysql.err.OperationalError(1049, "Unknown database 'f3ttown_test'")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Conn:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    monkeypatch.setattr("migrate.connect", lambda _settings: Conn())
    code = main(
        [
            "--env-file",
            str(env_file),
            "--migrations",
            str(migrations),
            "--mark-applied",
            "1",
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "does not exist" in captured.err
    assert captured.err.startswith("error:")


def test_from_environment_refuses_a_target_prefix(monkeypatch):
    monkeypatch.setenv("STAGE", "test")
    monkeypatch.setenv("F3_REGION_NAME", "f3ttown")
    monkeypatch.setenv("DATABASE_HOST", "db.example")
    monkeypatch.setenv("DATABASE_USER", "user")
    monkeypatch.setenv("DATABASE_PASSWORD", "secret")
    with pytest.raises(MigrationError, match="DATABASE_"):
        load_invocation(_args(from_environment=True, stage="test", prefix="TARGET"))


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


def test_crlf_and_bom_have_the_same_checksum(tmp_path: Path):
    (tmp_path / "0001_alpha.sql").write_bytes(b"SELECT 1;\n")
    lf = discover(tmp_path)[0].checksum
    (tmp_path / "0001_alpha.sql").write_bytes(b"\xef\xbb\xbfSELECT 1;\r\n")
    assert discover(tmp_path)[0].checksum == lf


def test_version_zero_is_rejected(tmp_path: Path):
    (tmp_path / "0000_alpha.sql").write_text("SELECT 1;\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="0001"):
        discover(tmp_path)


def test_partial_failure_names_statements_already_run():
    failing = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT ok; SELECT FAIL;")
    cursor = FakeCursor()
    cursor.fail_on = "FAIL"
    with pytest.raises(MigrationError, match="statements 1-1 of 2 already ran"):
        apply_pending(cursor, [failing])


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
    with pytest.raises(MigrationError, match="DELIMITER"):
        split_sql("delimiter $$\nSELECT 1;\n")
    with pytest.raises(MigrationError, match="DELIMITER"):
        split_sql("Delimiter //\nSELECT 1;\n")


def test_split_sql_refuses_unclosed_comment_string_and_identifier():
    with pytest.raises(MigrationError, match="comment"):
        split_sql("CREATE TABLE a (id INT);\n/* unclosed\nCREATE TABLE b (id INT);\n")
    with pytest.raises(MigrationError, match="string"):
        split_sql("SELECT 'abc;\n")
    with pytest.raises(MigrationError, match="string"):
        split_sql('SELECT "abc;\n')
    with pytest.raises(MigrationError, match="identifier"):
        split_sql("SELECT `abc;\n")
    assert split_sql("SELECT 1; -- note") == ["SELECT 1"]


def test_apply_records_only_after_success_and_stops_at_to():
    first = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT 1; SELECT 2;")
    second = Migration(2, "beta", Path("0002_beta.sql"), "def", "SELECT 3;")
    cursor = FakeCursor()
    applied = apply_pending(cursor, [first, second], to=1)
    assert applied.applied == [1]
    assert cursor.statements == ["SELECT 1", "SELECT 2"]
    assert cursor.recorded[0]["version"] == 1

    again = apply_pending(cursor, [first, second], to=None)
    assert again.applied == [2]


def test_apply_refuses_a_changed_checksum_and_skips_the_insert_on_failure():
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


def test_changed_checksum_past_to_fails_before_apply():
    first = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT 1;")
    second = Migration(2, "beta", Path("0002_beta.sql"), "def", "SELECT 2;")
    cursor = FakeCursor([{"version": 2, "checksum": "stale"}])
    with pytest.raises(MigrationError, match="0002_beta"):
        apply_pending(cursor, [first, second], to=1)
    assert cursor.statements == []


def test_ahead_version_warns_and_applies_nothing_else():
    first = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT 1;")
    cursor = FakeCursor(
        [
            {"version": 1, "checksum": "abc"},
            {"version": 9, "checksum": "future"},
        ]
    )
    result = apply_pending(cursor, [first])
    assert result.applied == []
    assert result.ahead == [9]
    assert cursor.statements == []


def test_check_reports_pending_changed_and_current():
    migration = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "SELECT 1;")
    pending = plan_history([migration], None)
    assert pending.pending == [1]
    assert plan_history([migration], {}).pending == [1]
    current = plan_history([migration], {1: "abc"})
    assert current.pending == []
    assert current.ahead == []
    with pytest.raises(MigrationError, match="checksum"):
        plan_history([migration], {1: "zzz"})


def _names(sql: str) -> list[str]:
    return created_names([Migration(1, "baseline", Path("0001_baseline.sql"), "x", sql)])


def test_created_names_finds_views_and_qualified_tables():
    view = (
        "CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`%` "
        "SQL SECURITY DEFINER VIEW `v` AS SELECT 1;"
    )
    dumped = (
        "/*!50001 CREATE ALGORITHM=UNDEFINED */\n"
        "/*!50013 DEFINER=`root`@`%` SQL SECURITY DEFINER */\n"
        "/*!50001 VIEW `v` AS select 1 */;"
    )
    assert _names(view) == ["v"]
    assert _names(dumped) == ["v"]
    assert _names("CREATE TABLE `f3ttown_test`.`aos` (id INT);") == ["aos"]
    assert _names("CREATE TABLE `my-table` (id INT);") == ["my-table"]
    assert _names("CREATE TABLE `t$x` (id INT);") == ["t$x"]
    assert _names("CREATE TABLE `db`.`my-table` (id INT);") == ["my-table"]
    assert _names("CREATE TABLE `na``me` (id INT);") == ["na`me"]
    assert _names("CREATE UNIQUE INDEX idx ON users (id);") == []
    with pytest.raises(MigrationError, match="cannot name"):
        _names("CREATE SOMETHING weird;")
    with pytest.raises(MigrationError, match="create nothing"):
        mark_applied(
            FakeCursor(),
            "f3ttown_test",
            [Migration(1, "baseline", Path("0001_baseline.sql"), "x", "SELECT 1;")],
            1,
            yes=False,
        )


def test_mark_applied_refuses_a_missing_view():
    sql = "CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v` AS SELECT 1;"
    migration = Migration(1, "baseline", Path("0001_baseline.sql"), "abc", sql)
    with pytest.raises(MigrationError, match="missing"):
        mark_applied(FakeCursor(), "f3ttown_test", [migration], 1, yes=False)


def test_mark_applied_dry_run_writes_nothing_and_yes_records_checksums():
    migration = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "CREATE TABLE users (id INT);")
    cursor = FakeCursor(present={"users"})
    marked = mark_applied(cursor, "f3ttown_test", [migration], 1, yes=False)
    assert marked == [1]
    assert cursor.recorded == []
    assert not any("schema_migrations" in statement for statement in cursor.statements)

    marked = mark_applied(cursor, "f3ttown_test", [migration], 1, yes=True)
    assert marked == [1]
    assert cursor.recorded == [{"version": 1, "checksum": "abc"}]


def test_mark_applied_refuses_rows_missing_tables_and_a_version_past_the_end():
    migration = Migration(1, "alpha", Path("0001_alpha.sql"), "abc", "CREATE TABLE users (id INT);")
    with pytest.raises(MigrationError, match="already has rows"):
        mark_applied(
            FakeCursor(recorded=[{"version": 1, "checksum": "abc"}], present={"users"}),
            "f3ttown_test",
            [migration],
            1,
            yes=True,
        )
    with pytest.raises(MigrationError, match="missing"):
        mark_applied(FakeCursor(), "f3ttown_test", [migration], 1, yes=False)
    with pytest.raises(MigrationError, match="past the last file"):
        mark_applied(FakeCursor(present={"users"}), "f3ttown_test", [migration], 2, yes=False)


class Connection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def cursor(self):
        return self.cursor_obj

    def close(self):
        return None


class ContextCursor(FakeCursor):
    def __init__(self, *args, use_error=None, bookkeeping_missing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_error = use_error
        self.bookkeeping_missing = bookkeeping_missing

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, args=None):
        text = " ".join(str(sql).split())
        if text.startswith("USE") and self.use_error:
            raise self.use_error
        if self.bookkeeping_missing and text.startswith("SELECT version, checksum"):
            raise RuntimeError("(1146, \"Table 'f3ttown_test.schema_migrations' doesn't exist\")")
        return super().execute(sql, args)


def _patch_connect(monkeypatch, cursor):
    monkeypatch.setattr("migrate.connect", lambda _settings: Connection(cursor))


def test_run_refuses_existing_tables_when_nothing_is_recorded(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_alpha.sql").write_text("SELECT 1;\n", encoding="utf-8")
    cursor = ContextCursor()
    cursor.other_tables = 4
    _patch_connect(monkeypatch, cursor)
    with pytest.raises(MigrationError, match="mark-applied"):
        run(
            migrations,
            "f3ttown_test",
            {"host": "h", "port": 4000, "user": "u", "password": "p", "tls": True},
            to=None,
            check=False,
        )
    assert not any(statement == "SELECT 1" for statement in cursor.statements)


def test_run_applies_pending_when_history_exists(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_alpha.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (migrations / "0002_beta.sql").write_text("SELECT 2;\n", encoding="utf-8")
    checksum = discover(migrations)[0].checksum
    cursor = ContextCursor(recorded=[{"version": 1, "checksum": checksum}])
    cursor.other_tables = 4
    _patch_connect(monkeypatch, cursor)
    result = run(
        migrations,
        "f3ttown_test",
        {"host": "h", "port": 4000, "user": "u", "password": "p", "tls": True},
        to=None,
        check=False,
    )
    assert result.applied == [2]
    assert "SELECT 1" not in cursor.statements
    assert "SELECT 2" in cursor.statements


def test_run_creates_the_database_with_unicode_collation(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_alpha.sql").write_text("SELECT 1;\n", encoding="utf-8")
    cursor = ContextCursor()
    _patch_connect(monkeypatch, cursor)
    result = run(
        migrations,
        "f3ttown_test",
        {"host": "h", "port": 4000, "user": "u", "password": "p", "tls": True},
        to=None,
        check=False,
    )
    assert result.applied == [1]
    assert cursor.statements[0] == (
        "CREATE DATABASE IF NOT EXISTS `f3ttown_test` "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )


def test_check_exit_codes_write_nothing(tmp_path, monkeypatch, capsys):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_alpha.sql").write_text("SELECT 1;\n", encoding="utf-8")
    checksum = discover(migrations)[0].checksum
    env_file = _deploy_file(tmp_path / ".env.deploy.test", "test")
    cases = [
        (ContextCursor(use_error=RuntimeError("(1049, \"Unknown database 'f3ttown_test'\")")), 1),
        (ContextCursor(bookkeeping_missing=True), 1),
        (ContextCursor(recorded=[{"version": 1, "checksum": checksum}]), 0),
        (ContextCursor(recorded=[{"version": 1, "checksum": "zzz"}]), 1),
        (
            ContextCursor(
                recorded=[
                    {"version": 1, "checksum": checksum},
                    {"version": 9, "checksum": "future"},
                ]
            ),
            0,
        ),
    ]
    for cursor, expected in cases:
        _patch_connect(monkeypatch, cursor)
        code = main(
            ["--env-file", str(env_file), "--migrations", str(migrations), "--check"]
        )
        assert code == expected
        assert not any(statement.startswith("CREATE") for statement in cursor.statements)
        assert not any(statement.startswith("INSERT") for statement in cursor.statements)
        capsys.readouterr()


def test_schema_assertion_must_match_the_derived_name(tmp_path, monkeypatch, capsys):
    env_file = _deploy_file(tmp_path / ".env.deploy.test", "test")
    monkeypatch.setattr("migrate.connect", lambda _settings: (_ for _ in ()).throw(AssertionError("connect")))
    code = main(["--env-file", str(env_file), "--schema", "f3ttown_prod"])
    assert code == 1
    assert "does not match" in capsys.readouterr().err


def test_rehearsal_file_reads_target_prefix(tmp_path):
    env_file = tmp_path / ".env.migration.rehearsal"
    env_file.write_text(
        "\n".join(
            [
                "F3_REGION_NAME=f3ttown",
                "TARGET_HOST=target.example",
                "TARGET_USER=tu",
                "TARGET_PASSWORD=tp",
                "TARGET_PORT=4000",
                "TARGET_TLS_ENABLED=true",
            ]
        ),
        encoding="utf-8",
    )
    schema, settings = load_invocation(_args(env_file=env_file, prefix="TARGET"))
    assert schema == "f3ttown_rehearsal"
    assert settings["host"] == "target.example"
    assert settings["user"] == "tu"
    assert settings["password"] == "tp"


def test_rehearsed_baseline_names_every_table_and_view():
    migrations = discover(_REPO / "db" / "migrations")
    assert [item.version for item in migrations] == [1, 2, 3]
    assert migrations[0].name == "baseline"
    assert migrations[1].name == "region_flag_defaults"
    assert migrations[2].name == "achievement_keys"
    sql = migrations[0].sql
    assert "DEFINER=" not in sql
    assert "f3ttown_" not in sql
    assert "FOREIGN KEY" not in sql.upper()
    assert "AUTO_INCREMENT=" not in sql
    assert "utf8mb4" in sql
    names = created_names(migrations)
    assert names == [
        "achievement_versions",
        "achievements_awarded",
        "achievements_list",
        "aos",
        "bd_attendance",
        "beatdowns",
        "interaction_claims",
        "qsignups_aos",
        "qsignups_features",
        "qsignups_master",
        "qsignups_regions",
        "qsignups_weekly",
        "region_config",
        "region_report_definitions",
        "region_schedules",
        "slack_bots",
        "slack_installations",
        "slack_oauth_states",
        "slackblast_users",
        "users",
        "welcome_deliveries",
        "achievements_view",
        "attendance_view",
        "backblast",
        "beatdown_info",
        "vw_aos_sort",
        "vw_master_events",
        "vw_weekly_events",
    ]
    assert all("SQL SECURITY INVOKER" in statement for statement in split_sql(sql) if "VIEW" in statement)
