#!/usr/bin/env python3
"""Turn a copied region schema into the shape of 0001_baseline.sql.

Dry run by default. ``--yes`` writes, and only to test or rehearsal.
``--compare`` creates and drops a scratch database named
``compare_scratch_<id>_<stage>`` on the same server, then reads the schema.

    python migration/convert_to_baseline.py --env-file migration/.env.migration.rehearsal
    python migration/convert_to_baseline.py --env-file migration/.env.migration.rehearsal --compare
    python migration/convert_to_baseline.py --env-file migration/.env.migration.test --yes
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "db"))
sys.path.insert(0, str(_REPO / "migration"))

from baseline_shape import (  # noqa: E402
    BASELINE,
    CONVERSION_SQL,
    QSIGNUPS_TABLES,
    differences,
    fetch_live,
    fetch_views,
    secondary_indexes,
)
from migrate import (  # noqa: E402
    MigrationError,
    connect,
    connection_settings,
    derived_schema,
    parse_env_file,
    stage_from_filename,
)

WRITABLE = ("test", "rehearsal")


def guard(path: Path, *, write: bool, allow_prod: bool = False) -> tuple[str, dict]:
    stage = stage_from_filename(path)
    if write and stage not in WRITABLE and not (stage == "prod" and allow_prod):
        raise MigrationError(f"refusing to convert stage {stage!r}; this tool writes test or rehearsal only")
    env = parse_env_file(path)
    schema = derived_schema(env.get("F3_REGION_NAME", ""), stage)
    if write and schema not in ("f3ttown_test", "f3ttown_rehearsal"):
        raise MigrationError(f"refusing schema {schema!r}")
    return schema, connection_settings(env, "TARGET")


def scratch_name(schema: str) -> str:
    """A new scratch database for one compare.

    The suffix is the stage (``_test``, ``_prod``, or ``_rehearsal``) so the
    name stays inside that stage user's grant. A schema that is not one of
    those stages, such as a local fixture, uses ``_test``.
    """
    stage = schema.rsplit("_", 1)[-1]
    if stage not in ("test", "prod", "rehearsal"):
        stage = "test"
    return f"compare_scratch_{secrets.token_hex(4)}_{stage}"


def compare_recorded(cursor, schema: str, settings: dict) -> list[str]:
    """Diff a live schema against the files recorded in schema_migrations.

    The expected shape is built by applying those files to a scratch database
    on the same server, then dropping it. Views are compared by name only.
    """
    cursor.execute(f"SELECT version FROM `{schema}`.`schema_migrations` ORDER BY version")
    versions = [int(row["version"]) for row in cursor.fetchall()]
    if not versions:
        raise MigrationError(f"{schema} has no recorded migrations to compare")
    expected, expected_views = _materialize(settings, versions, schema)
    return differences(
        fetch_live(cursor, schema),
        expected,
        live_views=fetch_views(cursor, schema),
        expected_views=expected_views,
    )


def _materialize(settings: dict, versions: list[int], schema: str) -> tuple[dict, set[str]]:
    from migrate import discover, split_sql

    temp = scratch_name(schema)
    chosen = [item for item in discover(BASELINE.parent) if item.version in set(versions)]
    conn = connect(settings)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{temp}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            try:
                cursor.execute(f"USE `{temp}`")
                for migration in chosen:
                    for statement in split_sql(migration.sql):
                        cursor.execute(statement)
                return fetch_live(cursor, temp), fetch_views(cursor, temp)
            finally:
                cursor.execute(f"DROP DATABASE IF EXISTS `{temp}`")
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a copied region schema toward 0001")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--yes", action="store_true", help="Write. Without this, only print.")
    parser.add_argument(
        "--compare",
        action="store_true",
        help=(
            "Diff against the migrations recorded on the schema. "
            "Creates and drops a scratch database named compare_scratch_<id>_<stage> "
            "on the same server. Views are compared by name only."
        ),
    )
    parser.add_argument(
        "--allow-prod",
        action="store_true",
        help="Required to convert f3ttown_prod. The cutover runbook is the only reason to pass this.",
    )
    args = parser.parse_args(argv)
    try:
        schema, settings = guard(
            args.env_file,
            write=args.yes and not args.compare,
            allow_prod=args.allow_prod,
        )
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.compare:
        conn = connect(settings)
        try:
            with conn.cursor() as cursor:
                found = compare_recorded(cursor, schema, settings)
        finally:
            conn.close()
        if found:
            print(f"{schema} differs from its recorded migrations:")
            for item in found:
                print(f"  {item}")
            return 1
        print(f"{schema} matches its recorded migrations")
        return 0
    print(f"-- drop every non-primary index on {', '.join(QSIGNUPS_TABLES)}")
    for statement in CONVERSION_SQL:
        print(statement + ";")
    if not args.yes:
        print("dry run only; pass --yes to write")
        return 0
    conn = connect(settings)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"USE `{schema}`")
            for table, index in secondary_indexes(cursor, schema, QSIGNUPS_TABLES):
                cursor.execute(f"ALTER TABLE `{table}` DROP INDEX `{index}`")
            for statement in CONVERSION_SQL:
                cursor.execute(statement)
        conn.commit()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"converted {schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
