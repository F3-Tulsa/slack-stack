"""Copy Tulsa's three test schemas into f3ttown_test. Does not drop anything.

The apps still read the old schemas. This only adds tables and rows beside
the regional data that is already in f3ttown_test. It refuses every env file
whose name does not end in .test, and it refuses any schema other than
f3ttown_test. Default is a dry run. --yes writes.

Bolt tables are copied from Slackblast first, then QSignups rows whose
client_id is not already present. Their autoincrement ids are not preserved
on the second copy. Nothing references those ids; slack_sdk looks up by
client_id.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_DB = Path(__file__).resolve().parent
sys.path.insert(0, str(_DB))

from migrate import (  # noqa: E402
    MigrationError,
    connection_settings,
    derived_schema,
    parse_env_file,
    stage_from_filename,
)

TARGET = "f3ttown_test"
SOURCES = {
    "paxminer": "paxminer_test",
    "slackblast": "slackblast_test",
    "qsignups": "qsignups_test",
}
PLAIN_TABLES = (
    ("slackblast_test", "slackblast_users"),
    ("slackblast_test", "welcome_deliveries"),
    ("slackblast_test", "interaction_claims"),
    ("qsignups_test", "qsignups_aos"),
    ("qsignups_test", "qsignups_features"),
    ("qsignups_test", "qsignups_master"),
    ("qsignups_test", "qsignups_regions"),
    ("qsignups_test", "qsignups_weekly"),
    ("paxminer_test", "region_report_definitions"),
    ("paxminer_test", "region_schedules"),
)
BOLT_TABLES = ("slack_bots", "slack_installations", "slack_oauth_states")
VIEWS = ("vw_aos_sort", "vw_master_events", "vw_weekly_events")
DEFINER = re.compile(r"\s*DEFINER\s*=\s*\S+", re.IGNORECASE)

# Not a numbered migration. 0001 is reserved for the rehearsed baseline.
REGION_CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS region_config (
    region VARCHAR(45) NOT NULL,
    schema_name VARCHAR(45) NULL,
    active TINYINT NULL,
    slack_token VARCHAR(512) NOT NULL,
    contact VARCHAR(45) NULL,
    scrape_backblasts TINYINT NULL,
    comments TEXT NULL,
    send_achievements TINYINT NULL,
    region_achievements_channel VARCHAR(100) NULL,
    NO_POST_THRESHOLD INT NULL,
    REMINDER_WEEKS INT NULL,
    HOME_AO_CAPTURE INT NULL,
    NO_Q_THRESHOLD_WEEKS INT NULL,
    NO_Q_THRESHOLD_POSTS INT NULL,
    timezone VARCHAR(45) NOT NULL DEFAULT 'America/Chicago',
    log_channel VARCHAR(100) NULL,
    team_id VARCHAR(100) NULL,
    workspace_name VARCHAR(100) NULL,
    sb_bot_token VARCHAR(512) NULL,
    email_enabled TINYINT NULL,
    email_server VARCHAR(100) NULL,
    email_server_port INT NULL,
    email_user VARCHAR(100) NULL,
    email_password LONGTEXT NULL,
    email_to VARCHAR(100) NULL,
    email_option_show TINYINT NULL,
    postie_format TINYINT NULL,
    editing_locked TINYINT NULL,
    default_destination VARCHAR(30) NULL,
    backblast_moleskin_template JSON NULL,
    preblast_moleskin_template JSON NULL,
    strava_enabled TINYINT NULL,
    custom_fields JSON NULL,
    welcome_dm_enable TINYINT NULL,
    welcome_dm_template JSON NULL,
    welcome_channel_enable TINYINT NULL,
    welcome_channel VARCHAR(100) NULL,
    post_achievements_to_ao TINYINT NULL,
    created DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
    updated DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (region)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def guard(path: Path) -> tuple[str, dict]:
    """Only the test env file, and only f3ttown_test."""
    if stage_from_filename(path) != "test":
        raise MigrationError(f"{path.name} is not a test env file")
    env = parse_env_file(path)
    schema = derived_schema(env.get("F3_REGION_NAME", ""), "test")
    if schema != TARGET:
        raise MigrationError(f"refusing schema {schema!r}; this copy is for {TARGET} only")
    return schema, connection_settings(env, "TARGET")


def _table_exists(cursor, schema: str, table: str) -> bool:
    cursor.execute(
        """
        SELECT TABLE_NAME AS name FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        """,
        (schema, table),
    )
    return cursor.fetchone() is not None


def _count(cursor, schema: str, table: str) -> int:
    cursor.execute(f"SELECT COUNT(*) AS c FROM `{schema}`.`{table}`")
    return int(cursor.fetchone()["c"])


def _columns(cursor, schema: str, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        ORDER BY ORDINAL_POSITION
        """,
        (schema, table),
    )
    return [row["name"] for row in cursor.fetchall()]


def copy_table(cursor, source: str, table: str, *, yes: bool) -> str:
    if _table_exists(cursor, TARGET, table):
        return f"skip {TARGET}.{table}: already present"
    if yes:
        cursor.execute(f"CREATE TABLE `{TARGET}`.`{table}` LIKE `{source}`.`{table}`")
        cursor.execute(f"INSERT INTO `{TARGET}`.`{table}` SELECT * FROM `{source}`.`{table}`")
    return f"copy {source}.{table} -> {TARGET}.{table} ({_count(cursor, source, table)} rows)"


def copy_bolt(cursor, table: str, *, yes: bool) -> list[str]:
    """Slackblast rows first, including ids. QSignups rows after, without ids."""
    notes = []
    if not _table_exists(cursor, TARGET, table):
        notes.append(copy_table(cursor, "slackblast_test", table, yes=yes))
    else:
        notes.append(f"skip {TARGET}.{table}: already present, QSignups rows still checked")
    columns = [name for name in _columns(cursor, "qsignups_test", table) if name != "id"]
    quoted = ", ".join(f"`{name}`" for name in columns)
    insert = (
        f"INSERT INTO `{TARGET}`.`{table}` ({quoted}) "
        f"SELECT {quoted} FROM `qsignups_test`.`{table}` s "
        f"WHERE s.client_id NOT IN (SELECT client_id FROM `{TARGET}`.`{table}`)"
    )
    if "client_id" not in columns:
        insert = (
            f"INSERT INTO `{TARGET}`.`{table}` ({quoted}) "
            f"SELECT {quoted} FROM `qsignups_test`.`{table}`"
        )
    pending = _count(cursor, "qsignups_test", table)
    notes.append(f"merge qsignups_test.{table} ({pending} source rows)")
    if yes and _table_exists(cursor, TARGET, table):
        cursor.execute(insert)
    return notes


def copy_views(cursor, *, yes: bool) -> list[str]:
    notes = []
    for view in VIEWS:
        cursor.execute(f"SHOW CREATE VIEW `qsignups_test`.`{view}`")
        row = cursor.fetchone()
        ddl = row.get("Create View") or row.get("CREATE VIEW") or ""
        ddl = DEFINER.sub("", ddl)
        ddl = ddl.replace("`qsignups_test`.", "")
        notes.append(f"view {view}")
        if yes:
            cursor.execute(f"USE `{TARGET}`")
            cursor.execute(f"DROP VIEW IF EXISTS `{view}`")
            cursor.execute(ddl)
    return notes


def copy_region_config(cursor, *, yes: bool) -> str:
    created = ""
    if not _table_exists(cursor, TARGET, "region_config"):
        if yes:
            cursor.execute(REGION_CONFIG_DDL)
        created = "create region_config\n"
    elif _count(cursor, TARGET, "region_config"):
        return "skip region_config: already has a row"
    insert = f"""
        INSERT INTO `{TARGET}`.region_config (
            region, schema_name, active, slack_token, contact, scrape_backblasts,
            comments, send_achievements, region_achievements_channel,
            NO_POST_THRESHOLD, REMINDER_WEEKS, HOME_AO_CAPTURE,
            NO_Q_THRESHOLD_WEEKS, NO_Q_THRESHOLD_POSTS, timezone, log_channel,
            team_id, workspace_name, sb_bot_token,
            email_enabled, email_server, email_server_port,
            email_user, email_password, email_to, email_option_show, postie_format,
            editing_locked, default_destination, backblast_moleskin_template,
            preblast_moleskin_template, strava_enabled, custom_fields,
            welcome_dm_enable, welcome_dm_template, welcome_channel_enable,
            welcome_channel, post_achievements_to_ao,
            created, updated
        )
        SELECT
            p.region, p.schema_name, p.active, p.slack_token, p.contact,
            p.scrape_backblasts, p.comments, p.send_achievements, p.achievement_channel,
            p.NO_POST_THRESHOLD, p.REMINDER_WEEKS, p.HOME_AO_CAPTURE,
            p.NO_Q_THRESHOLD_WEEKS, p.NO_Q_THRESHOLD_POSTS, p.timezone, p.log_channel,
            s.team_id, s.workspace_name, s.bot_token,
            s.email_enabled, s.email_server, s.email_server_port,
            s.email_user, s.email_password, s.email_to, s.email_option_show,
            s.postie_format, s.editing_locked, s.default_destination,
            s.backblast_moleskin_template, s.preblast_moleskin_template,
            s.strava_enabled, s.custom_fields, s.welcome_dm_enable, s.welcome_dm_template,
            s.welcome_channel_enable, s.welcome_channel,
            s.post_achievements_to_ao, s.created, s.updated
        FROM paxminer_test.regions p
        LEFT JOIN slackblast_test.regions s ON s.paxminer_schema = p.schema_name
        WHERE p.region = 'f3ttown'
    """
    if yes:
        cursor.execute(insert)
    return created + "insert f3ttown into region_config from paxminer_test and slackblast_test"


def run_copy(cursor, *, yes: bool) -> list[str]:
    notes = [copy_table(cursor, source, table, yes=yes) for source, table in PLAIN_TABLES]
    for table in BOLT_TABLES:
        notes.extend(copy_bolt(cursor, table, yes=yes))
    notes.extend(copy_views(cursor, yes=yes))
    notes.append(copy_region_config(cursor, yes=yes))
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy test schemas into f3ttown_test")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--yes", action="store_true", help="Write. Without this, only print.")
    args = parser.parse_args(argv)
    try:
        _schema, settings = guard(args.env_file)
        from migrate import connect

        conn = connect(settings)
        try:
            with conn.cursor() as cursor:
                for line in run_copy(cursor, yes=args.yes):
                    print(line)
        finally:
            conn.close()
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not args.yes:
        print("dry run only; pass --yes to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
