#!/usr/bin/env python3
"""Create an empty region schema, apply numbered SQL, and seed missing defaults.

Seeds reports and achievements only when those tables are empty, so a later
run does not put back a builtin an admin deleted. The Slack token is left
empty; the Lambda cold start encrypts and writes it.

Refuses ``f3ttown_test`` and ``f3ttown_prod``. Deploy does not call this.

    python db/fresh_install.py --env-file .env.deploy.test

``--timezone`` overrides ``F3_TIMEZONE``. Both default to America/Chicago.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "db"))
sys.path.insert(0, str(_REPO / "PAXminer"))

from migrate import MigrationError, connect, load_invocation, run  # noqa: E402

TULSA_SCHEMAS = frozenset({"f3ttown_test", "f3ttown_prod"})


def _paxminer():
    from achievements.activity import activity_filter_from_rule, activity_legacy_mirror
    from achievements.achievement_rules import ACHIEVEMENT_SEEDS
    from achievements.range import resolve_stored_range
    from achievements.versions import insert_version
    from scheduling import BUILTIN_DEFINITIONS, DEFAULT_SCHEDULES

    return (
        activity_filter_from_rule,
        activity_legacy_mirror,
        ACHIEVEMENT_SEEDS,
        resolve_stored_range,
        insert_version,
        BUILTIN_DEFINITIONS,
        DEFAULT_SCHEDULES,
    )


def _one(cursor, sql: str, params: tuple = ()):
    cursor.execute(sql, params)
    return cursor.fetchone()


def seed_region_config(cursor, schema: str, *, region: str, team_id: str, timezone: str) -> str:
    if _one(cursor, "SELECT region FROM region_config LIMIT 1"):
        return "kept"
    cursor.execute(
        """
        INSERT INTO region_config
          (region, schema_name, active, slack_token, timezone, team_id, send_achievements,
           email_enabled, email_option_show, editing_locked, postie_format,
           strava_enabled, default_destination, post_achievements_to_ao)
        VALUES (%s, %s, 1, '', %s, %s, 0, 0, 0, 0, 1, 1, 'ao_channel', 0)
        """,
        (region, schema, timezone, team_id),
    )
    return "inserted"


def seed_qsignups_region(cursor, *, team_id: str, timezone: str) -> str:
    if _one(cursor, "SELECT id FROM qsignups_regions WHERE team_id=%s", (team_id,)):
        return "kept"
    cursor.execute(
        "INSERT INTO qsignups_regions (team_id, timezone) VALUES (%s, %s)",
        (team_id, timezone),
    )
    return "inserted"


def seed_reports(cursor, schema: str) -> dict[str, int]:
    existing = _one(cursor, "SELECT COUNT(*) AS c FROM region_report_definitions")
    if existing and int(existing["c"]):
        return {"definitions": 0, "schedules": 0}
    *_, definitions, schedules = _paxminer()
    inserted_definitions = 0
    inserted_schedules = 0
    code_to_id: dict[str, int] = {}
    for item in definitions:
        cursor.execute(
            """
            INSERT INTO region_report_definitions
              (schema_name, code, name, report_type, is_builtin, is_customized, time_window_type, top_n)
            VALUES (%s, %s, %s, %s, 1, 0, %s, %s)
            """,
            (
                schema,
                item["code"],
                item["name"],
                item["report_type"],
                item.get("time_window_type"),
                item.get("top_n"),
            ),
        )
        inserted_definitions += 1
        found = _one(
            cursor,
            "SELECT id FROM region_report_definitions WHERE schema_name=%s AND code=%s",
            (schema, item["code"]),
        )
        code_to_id[item["code"]] = int(found["id"])
    for item in schedules:
        definition_id = code_to_id[item["code"]]
        cursor.execute(
            """
            INSERT INTO region_schedules
              (schema_name, report_definition_id, destination_type, destination_channels,
               frequency_type, month_day_mode, time_of_day, enabled)
            VALUES (%s, %s, %s, NULL, %s, %s, %s, %s)
            """,
            (
                schema,
                definition_id,
                item["destination_type"],
                item.get("frequency_type") or "monthly",
                item.get("month_day_mode") or "first",
                item.get("time_of_day") or "07:00:00",
                1 if item.get("enabled", True) else 0,
            ),
        )
        inserted_schedules += 1
    return {"definitions": inserted_definitions, "schedules": inserted_schedules}


def seed_achievements(cursor, schema: str) -> int:
    (
        activity_filter_from_rule,
        activity_legacy_mirror,
        seeds,
        resolve_stored_range,
        insert_version,
        _,
        _,
    ) = _paxminer()
    existing = _one(cursor, "SELECT COUNT(*) AS c FROM achievements_list")
    if existing and int(existing["c"]):
        return 0
    added = 0
    today = date.today().isoformat()
    for seed in seeds:
        spec = activity_filter_from_rule(seed)
        cursor.execute(
            """
            INSERT INTO achievements_list
              (name, description, verb, code, metric, activity, period, threshold, enabled, emoji)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
            """,
            (
                seed["name"],
                seed["description"],
                seed["verb"],
                seed["code"],
                seed["metric"],
                activity_legacy_mirror(spec, version=1)[:32],
                seed["period"],
                int(seed["threshold"]),
                seed.get("emoji"),
            ),
        )
        achievement_id = int(cursor.lastrowid)
        mode, from_date, to_date = resolve_stored_range(
            {"range_mode": "all_attendance"},
            first_created=today,
            version_created=today,
            minting=False,
        )
        insert_version(
            cursor,
            schema,
            achievement_id=achievement_id,
            code=seed["code"],
            metric=seed["metric"],
            activity_filter=spec,
            period=seed["period"],
            threshold=int(seed["threshold"]),
            effective_from=date.fromisoformat(from_date) if from_date else None,
            effective_to=date.fromisoformat(to_date) if to_date else None,
            created_by="fresh-install",
            version=1,
            range_mode=mode,
        )
        added += 1
    return added


def seed(cursor, schema: str, *, region: str, team_id: str, timezone: str) -> dict:
    cursor.execute(f"USE `{schema}`")
    return {
        "region_config": seed_region_config(cursor, schema, region=region, team_id=team_id, timezone=timezone),
        "qsignups_regions": seed_qsignups_region(cursor, team_id=team_id, timezone=timezone),
        "reports": seed_reports(cursor, schema),
        "achievements": seed_achievements(cursor, schema),
    }


def fresh_install(
    directory: Path,
    schema: str,
    settings: dict,
    *,
    region: str,
    team_id: str,
    timezone: str,
    to: int | None,
) -> dict:
    if schema in TULSA_SCHEMAS:
        raise MigrationError(f"refusing {schema}; fresh install does not run on Tulsa")
    if not team_id:
        raise MigrationError("F3_REGION_SLACK_TEAM_ID is required to seed qsignups_regions")
    applied = run(directory, schema, settings, to=to, check=False)
    conn = connect(settings)
    conn.autocommit(False)
    try:
        with conn.cursor() as cursor:
            summary = seed(cursor, schema, region=region, team_id=team_id, timezone=timezone)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    summary["applied"] = getattr(applied, "applied", None) or []
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and seed an empty region schema")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--prefix", choices=("DATABASE", "TARGET"), default="DATABASE")
    parser.add_argument("--to", type=int, default=None)
    parser.add_argument("--allow-prod", action="store_true")
    parser.add_argument(
        "--timezone",
        default="",
        help="Region timezone. Defaults to F3_TIMEZONE, then America/Chicago.",
    )
    parser.set_defaults(from_environment=False, stage=None, schema=None)
    args = parser.parse_args(argv)
    try:
        schema, settings = load_invocation(args)
        from migrate import parse_env_file

        env = parse_env_file(args.env_file)
        summary = fresh_install(
            Path(__file__).resolve().parent / "migrations",
            schema,
            settings,
            region=env["F3_REGION_NAME"],
            team_id=env.get("F3_REGION_SLACK_TEAM_ID", ""),
            timezone=args.timezone or env.get("F3_TIMEZONE") or "America/Chicago",
            to=args.to,
        )
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "fresh install "
        f"applied={','.join(f'{n:04d}' for n in summary['applied']) or 'none'} "
        f"region_config={summary['region_config']} "
        f"qsignups_regions={summary['qsignups_regions']} "
        f"definitions={summary['reports']['definitions']} "
        f"schedules={summary['reports']['schedules']} "
        f"achievements={summary['achievements']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
