"""Copy one region's app schemas into f3ttown_<stage>. Does not drop anything.

The apps still read the old schemas. This only adds tables and rows beside
the regional data that is already in the region schema. It writes ``test`` or
``rehearsal`` and refuses ``prod``. The region name has to be ``f3ttown``.
Default is a dry run. --yes writes.

Bolt tables are copied from Slackblast first, then QSignups rows whose
client_id is not already present. Their autoincrement ids are not preserved
on the second copy. Nothing references those ids; slack_sdk looks up by
client_id.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "db"))

from migrate import (  # noqa: E402
    MigrationError,
    connection_settings,
    derived_schema,
    parse_env_file,
    stage_from_filename,
)

REGION = "f3ttown"
WRITABLE_STAGES = ("test", "rehearsal")


@dataclass(frozen=True)
class CopyTarget:
    stage: str
    region: str
    target: str
    paxminer: str
    slackblast: str
    qsignups: str


def target_for(stage: str) -> CopyTarget:
    if stage not in WRITABLE_STAGES:
        raise MigrationError(f"refusing stage {stage!r}; this copy writes test or rehearsal only")
    return CopyTarget(
        stage=stage,
        region=REGION,
        target=f"{REGION}_{stage}",
        paxminer=f"paxminer_{stage}",
        slackblast=f"slackblast_{stage}",
        qsignups=f"qsignups_{stage}",
    )


TEST = target_for("test")
TARGET = TEST.target


def plain_tables(dest: CopyTarget) -> tuple[tuple[str, str], ...]:
    return (
        (dest.slackblast, "slackblast_users"),
        (dest.slackblast, "welcome_deliveries"),
        (dest.slackblast, "interaction_claims"),
        (dest.qsignups, "qsignups_aos"),
        (dest.qsignups, "qsignups_features"),
        (dest.qsignups, "qsignups_master"),
        (dest.qsignups, "qsignups_regions"),
        (dest.qsignups, "qsignups_weekly"),
        (dest.paxminer, "region_report_definitions"),
        (dest.paxminer, "region_schedules"),
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


def guard(path: Path) -> tuple[CopyTarget, dict]:
    """A test or rehearsal env file whose region schema is f3ttown_<stage>."""
    dest = target_for(stage_from_filename(path))
    env = parse_env_file(path)
    schema = derived_schema(env.get("F3_REGION_NAME", ""), dest.stage)
    if schema != dest.target:
        raise MigrationError(f"refusing schema {schema!r}; this copy is for {dest.target} only")
    return dest, connection_settings(env, "TARGET")


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


def copy_table(cursor, source: str, table: str, *, dest: CopyTarget, yes: bool) -> str:
    source_count = _count(cursor, source, table)
    if _table_exists(cursor, dest.target, table):
        target_count = _count(cursor, dest.target, table)
        if target_count != source_count:
            raise MigrationError(
                f"{table}: target has {target_count} rows and source has {source_count}; "
                f"drop it in {dest.target} and run again"
            )
        return f"skip {dest.target}.{table}: source {source_count} target {target_count}"
    if yes:
        cursor.execute(f"CREATE TABLE `{dest.target}`.`{table}` LIKE `{source}`.`{table}`")
        cursor.execute(
            f"INSERT INTO `{dest.target}`.`{table}` SELECT * FROM `{source}`.`{table}`"
        )
        target_count = _count(cursor, dest.target, table)
        return (
            f"copy {source}.{table} -> {dest.target}.{table} "
            f"(source {source_count}, target {target_count})"
        )
    return f"copy {source}.{table} -> {dest.target}.{table} ({source_count} rows)"


def copy_bolt(cursor, table: str, *, dest: CopyTarget, yes: bool) -> list[str]:
    """Slackblast rows first, including ids. QSignups rows after, without ids."""
    notes = []
    if not _table_exists(cursor, dest.target, table):
        notes.append(copy_table(cursor, dest.slackblast, table, dest=dest, yes=yes))
    else:
        source_count = _count(cursor, dest.slackblast, table)
        target_count = _count(cursor, dest.target, table)
        if target_count == 0 and source_count > 0:
            raise MigrationError(
                f"{table}: target has 0 rows and source has {source_count}; "
                f"drop it in {dest.target} and run again"
            )
        notes.append(f"skip {dest.target}.{table}: source {source_count} target {target_count}")
    if table == "slack_oauth_states":
        notes.append(f"skip {dest.qsignups}.slack_oauth_states: single-use, not merged")
        return notes
    columns = [name for name in _columns(cursor, dest.qsignups, table) if name != "id"]
    quoted = ", ".join(f"`{name}`" for name in columns)
    insert = (
        f"INSERT INTO `{dest.target}`.`{table}` ({quoted}) "
        f"SELECT {quoted} FROM `{dest.qsignups}`.`{table}` s "
        f"WHERE s.client_id NOT IN (SELECT client_id FROM `{dest.target}`.`{table}`)"
    )
    if "client_id" not in columns:
        insert = (
            f"INSERT INTO `{dest.target}`.`{table}` ({quoted}) "
            f"SELECT {quoted} FROM `{dest.qsignups}`.`{table}`"
        )
    pending = _count(cursor, dest.qsignups, table)
    notes.append(f"merge {dest.qsignups}.{table} ({pending} source rows)")
    if yes and _table_exists(cursor, dest.target, table):
        cursor.execute(insert)
    return notes


def copy_views(cursor, *, dest: CopyTarget, yes: bool) -> list[str]:
    notes = []
    for view in VIEWS:
        cursor.execute(f"SHOW CREATE VIEW `{dest.qsignups}`.`{view}`")
        row = cursor.fetchone()
        ddl = row.get("Create View") or row.get("CREATE VIEW") or ""
        ddl = DEFINER.sub("", ddl)
        ddl = ddl.replace(f"`{dest.qsignups}`.", "")
        notes.append(f"view {view}")
        if yes:
            cursor.execute(f"USE `{dest.target}`")
            cursor.execute(f"DROP VIEW IF EXISTS `{view}`")
            cursor.execute(ddl)
    return notes


def _require_one_region_row(cursor, schema: str, where: str, param: str) -> None:
    cursor.execute(
        f"SELECT COUNT(*) AS c FROM `{schema}`.`regions` WHERE {where}",
        (param,),
    )
    count = int(cursor.fetchone()["c"])
    if count != 1:
        raise MigrationError(f"{schema}.regions for {param}: expected 1 row, found {count}")


def copy_region_config(cursor, *, dest: CopyTarget, yes: bool) -> str:
    _require_one_region_row(cursor, dest.paxminer, "region=%s", dest.region)
    _require_one_region_row(cursor, dest.slackblast, "paxminer_schema=%s", dest.target)
    cursor.execute(
        f"SELECT schema_name AS name FROM `{dest.paxminer}`.`regions` WHERE region=%s",
        (dest.region,),
    )
    found = cursor.fetchone()
    schema_name = found["name"] if found else None
    if schema_name != dest.target:
        raise MigrationError(
            f"{dest.paxminer}.regions.schema_name for {dest.region} is {schema_name!r}; "
            f"expected {dest.target}"
        )
    created = ""
    if not _table_exists(cursor, dest.target, "region_config"):
        if yes:
            cursor.execute(
                REGION_CONFIG_DDL.replace(
                    "CREATE TABLE IF NOT EXISTS region_config",
                    f"CREATE TABLE IF NOT EXISTS `{dest.target}`.`region_config`",
                    1,
                )
            )
        created = "create region_config\n"
    elif _count(cursor, dest.target, "region_config"):
        return "skip region_config: already has a row"
    insert = f"""
        INSERT INTO `{dest.target}`.region_config (
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
        FROM `{dest.paxminer}`.regions p
        INNER JOIN `{dest.slackblast}`.regions s ON s.paxminer_schema = p.schema_name
        WHERE p.region = %s
    """
    if yes:
        cursor.execute(insert, (dest.region,))
        if int(cursor.rowcount) != 1:
            raise MigrationError(
                f"region_config insert changed {cursor.rowcount} rows; expected 1"
            )
    return (
        created
        + f"insert {dest.region} into region_config from {dest.paxminer} and {dest.slackblast}"
    )


def run_copy(cursor, dest: CopyTarget, *, yes: bool) -> list[str]:
    notes = [
        copy_table(cursor, source, table, dest=dest, yes=yes)
        for source, table in plain_tables(dest)
    ]
    for table in BOLT_TABLES:
        notes.extend(copy_bolt(cursor, table, dest=dest, yes=yes))
    notes.extend(copy_views(cursor, dest=dest, yes=yes))
    notes.append(copy_region_config(cursor, dest=dest, yes=yes))
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy app schemas into f3ttown_<stage>")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--yes", action="store_true", help="Write. Without this, only print.")
    args = parser.parse_args(argv)
    try:
        dest, settings = guard(args.env_file)
        from migrate import connect

        conn = connect(settings)
        try:
            with conn.cursor() as cursor:
                for line in run_copy(cursor, dest, yes=args.yes):
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
