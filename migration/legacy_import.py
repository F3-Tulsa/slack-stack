#!/usr/bin/env python3
"""Copy rows from an old-layout region into an empty baseline schema.

The runner creates the tables. This script never runs DDL, never drops, and
refuses a target table that already has rows. The target schema must match the
env file and must record exactly version 1. Token columns, including
``google_auth_data``, are not copied.

    python migration/legacy_import.py --env-file migration/.env.migration.test \\
        --source-schema <old regional schema> \\
        --qsignups-schema <old qsignups schema> \\
        --team-id <slack team> \\
        --target-schema <region>_test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "db"))

from migrate import MigrationError, connect, load_invocation  # noqa: E402

REGIONAL_TABLES = ("users", "aos", "beatdowns", "bd_attendance")
QSIGNUPS_TABLES = (
    "qsignups_regions",
    "qsignups_aos",
    "qsignups_weekly",
    "qsignups_master",
    "qsignups_features",
)
SKIP_COLUMNS = frozenset({"bot_token", "slack_token", "user_token", "google_auth_data"})


def columns(cursor, schema: str, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        ORDER BY ORDINAL_POSITION
        """,
        (schema, table),
    )
    return [row["name"] for row in cursor.fetchall()]


def row_count(cursor, schema: str, table: str) -> int:
    if not columns(cursor, schema, table):
        return 0
    cursor.execute(f"SELECT COUNT(*) AS c FROM `{schema}`.`{table}`")
    return int(cursor.fetchone()["c"])


def assert_targets_empty(cursor, target: str, tables: tuple[str, ...]) -> None:
    occupied = [table for table in tables if row_count(cursor, target, table)]
    if occupied:
        raise MigrationError(
            "refusing to import into a schema that already has rows in " + ", ".join(occupied)
        )


def require_baseline(cursor, target: str) -> None:
    cursor.execute(f"SELECT version FROM `{target}`.`schema_migrations` ORDER BY version")
    versions = [int(row["version"]) for row in cursor.fetchall()]
    if versions != [1]:
        raise MigrationError(
            f"{target} must record exactly version 1 before import, found {versions or 'nothing'}"
        )


def copy_table(cursor, source: str, target: str, table: str, *, where: str = "", params: tuple = ()) -> int:
    source_columns = columns(cursor, source, table)
    if not source_columns:
        return 0
    target_columns = set(columns(cursor, target, table))
    dropped = [name for name in source_columns if name not in target_columns and name not in SKIP_COLUMNS]
    if dropped:
        print(f"skipping {source}.{table} columns not in {target}: {', '.join(dropped)}")
    shared = [name for name in source_columns if name in target_columns and name not in SKIP_COLUMNS]
    if not shared:
        return 0
    quoted = ", ".join(f"`{name}`" for name in shared)
    cursor.execute(f"SELECT {quoted} FROM `{source}`.`{table}`{where}", params)
    rows = cursor.fetchall()
    if not rows:
        return 0
    placeholders = ", ".join(["%s"] * len(shared))
    for row in rows:
        cursor.execute(
            f"INSERT INTO `{target}`.`{table}` ({quoted}) VALUES ({placeholders})",
            tuple(row[name] for name in shared),
        )
    return len(rows)


def _region_ids(cursor, schema: str, team_id: str) -> list:
    if "id" not in columns(cursor, schema, "qsignups_regions"):
        return []
    cursor.execute(f"SELECT id FROM `{schema}`.`qsignups_regions` WHERE team_id=%s", (team_id,))
    return [row["id"] for row in cursor.fetchall()]


def import_rows(cursor, *, source_schema: str, qsignups_schema: str, target_schema: str, team_id: str) -> dict[str, int]:
    tables = REGIONAL_TABLES + QSIGNUPS_TABLES
    require_baseline(cursor, target_schema)
    assert_targets_empty(cursor, target_schema, tables)
    copied = {table: copy_table(cursor, source_schema, target_schema, table) for table in REGIONAL_TABLES}
    region_ids = _region_ids(cursor, qsignups_schema, team_id)
    for table in QSIGNUPS_TABLES:
        if table == "qsignups_features":
            if not region_ids:
                copied[table] = 0
                continue
            marks = ", ".join(["%s"] * len(region_ids))
            copied[table] = copy_table(
                cursor,
                qsignups_schema,
                target_schema,
                table,
                where=f" WHERE `region_id` IN ({marks})",
                params=tuple(region_ids),
            )
            continue
        if "team_id" in columns(cursor, qsignups_schema, table):
            copied[table] = copy_table(
                cursor,
                qsignups_schema,
                target_schema,
                table,
                where=" WHERE `team_id`=%s",
                params=(team_id,),
            )
        else:
            copied[table] = copy_table(cursor, qsignups_schema, target_schema, table)
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy old-layout rows into an empty baseline schema")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--prefix", choices=("DATABASE", "TARGET"), default="DATABASE")
    parser.add_argument("--allow-prod", action="store_true")
    parser.add_argument("--source-schema", required=True)
    parser.add_argument("--qsignups-schema", required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--target-schema", required=True)
    parser.set_defaults(from_environment=False, stage=None, schema=None)
    args = parser.parse_args(argv)
    try:
        derived, settings = load_invocation(args)
        if args.target_schema != derived:
            raise MigrationError(
                f"--target-schema {args.target_schema} does not match {derived} from the env file"
            )
        conn = connect(settings)
        conn.autocommit(False)
        try:
            with conn.cursor() as cursor:
                copied = import_rows(
                    cursor,
                    source_schema=args.source_schema,
                    qsignups_schema=args.qsignups_schema,
                    target_schema=args.target_schema,
                    team_id=args.team_id,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("imported " + ", ".join(f"{name}={count}" for name, count in copied.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
