"""Seed and edit helpers for the report scheduler tables.

db/migrations/0001_baseline.sql creates region_report_definitions and
region_schedules; this module only reads and writes their rows.
"""

from __future__ import annotations

import logging
from typing import Any

from scheduling import (
    BUILTIN_DEFINITIONS,
    DEFAULT_SCHEDULES,
    DEFAULT_TIMEZONE,
)

LOG = logging.getLogger(__name__)


def _table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        """,
        (schema, table),
    )
    return int(cur.fetchone()["c"]) > 0


def upsert_builtin_definitions(
    cur,
    pm_schema: str,
    regional_schema: str,
    *,
    reset_customized: bool = False,
) -> dict[str, int]:
    """Upsert builtin definitions by (schema_name, code). Return code -> id map.

    When reset_customized=False (Add Missing Defaults merge), rows an admin has
    customized (is_customized=1) keep their name/window; only missing codes are
    inserted and non-customized builtins are refreshed from JSON.

    When reset_customized=True, overwrite name/window and clear is_customized.
    """
    code_to_id: dict[str, int] = {}
    for d in BUILTIN_DEFINITIONS:
        cur.execute(
            f"""
            SELECT id, is_customized FROM `{pm_schema}`.`region_report_definitions`
            WHERE schema_name=%s AND code=%s
            """,
            (regional_schema, d["code"]),
        )
        existing = cur.fetchone()
        customized = bool(existing and int(existing.get("is_customized") or 0))
        if existing and customized and not reset_customized:
            code_to_id[d["code"]] = int(existing["id"])
            LOG.info(
                "  keep customized definition schema=%s code=%s id=%s",
                regional_schema,
                d["code"],
                existing["id"],
            )
            continue
        action = "update" if existing else "insert"
        if existing:
            cur.execute(
                f"""
                UPDATE `{pm_schema}`.`region_report_definitions`
                SET name=%s, report_type=%s, is_builtin=1, is_customized=0,
                    time_window_type=%s, top_n=%s
                WHERE id=%s
                """,
                (
                    d["name"],
                    d["report_type"],
                    d.get("time_window_type"),
                    d.get("top_n"),
                    existing["id"],
                ),
            )
            code_to_id[d["code"]] = int(existing["id"])
        else:
            cur.execute(
                f"""
                INSERT INTO `{pm_schema}`.`region_report_definitions`
                  (schema_name, code, name, report_type, is_builtin, is_customized,
                   time_window_type, top_n)
                VALUES (%s, %s, %s, %s, 1, 0, %s, %s)
                """,
                (
                    regional_schema,
                    d["code"],
                    d["name"],
                    d["report_type"],
                    d.get("time_window_type"),
                    d.get("top_n"),
                ),
            )
            cur.execute(
                f"""
                SELECT id FROM `{pm_schema}`.`region_report_definitions`
                WHERE schema_name=%s AND code=%s
                """,
                (regional_schema, d["code"]),
            )
            row = cur.fetchone()
            code_to_id[d["code"]] = int(row["id"])
        LOG.info(
            "  %s definition schema=%s code=%s name=%r report_type=%s window=%s",
            action,
            regional_schema,
            d["code"],
            d["name"],
            d["report_type"],
            d.get("time_window_type"),
        )
    return code_to_id


def seed_default_schedules(
    cur,
    pm_schema: str,
    region: dict[str, Any],
    *,
    merge_only: bool = True,
    skip_if_any_schedules: bool = False,
) -> int:
    """
    Seed default schedules for one region from report_defaults.json.

    Defaults are enabled; specific_channels items seed with empty destinations
    and skip until an admin picks a channel. dm_all_pax / all_ao_channels will
    fire on the next due tick unless disabled.

    When merge_only=True (Add Missing Defaults), skip inserting a default whose
    definition already has at least one schedule row (idempotent restore).

    When skip_if_any_schedules=True (initial migration), skip inserting schedules
    if the region already has any rows (definitions are still upserted).

    Returns number of schedule rows inserted.
    """
    regional = region.get("schema_name") or ""
    if not regional:
        return 0
    code_to_id = upsert_builtin_definitions(cur, pm_schema, regional)
    if skip_if_any_schedules:
        cur.execute(
            f"SELECT COUNT(*) AS c FROM `{pm_schema}`.`region_schedules` WHERE schema_name=%s",
            (regional,),
        )
        if int(cur.fetchone()["c"]) > 0:
            LOG.info(
                "Skip schedule seed schema=%s — schedules already present",
                regional,
            )
            return 0
    inserted = 0
    for item in DEFAULT_SCHEDULES:
        def_id = code_to_id[item["code"]]
        if merge_only:
            cur.execute(
                f"""
                SELECT COUNT(*) AS c FROM `{pm_schema}`.`region_schedules`
                WHERE schema_name=%s AND report_definition_id=%s
                """,
                (regional, def_id),
            )
            if int(cur.fetchone()["c"]) > 0:
                LOG.info(
                    "Skip schedule seed schema=%s code=%s — definition already scheduled",
                    regional,
                    item["code"],
                )
                continue
        enabled = 1 if item.get("enabled", True) else 0
        dest_type = item["destination_type"]
        # specific_channels start empty; admin must set a channel before posts fire.
        dest_channels = None
        freq = item.get("frequency_type") or "monthly"
        month_mode = item.get("month_day_mode") or "first"
        tod = item.get("time_of_day") or "07:00:00"
        cur.execute(
            f"""
            INSERT INTO `{pm_schema}`.`region_schedules`
              (schema_name, report_definition_id, destination_type, destination_channels,
               frequency_type, month_day_mode, time_of_day, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (regional, def_id, dest_type, dest_channels, freq, month_mode, tod, enabled),
        )
        inserted += 1
        LOG.info(
            "Seeded schedule schema=%s code=%s enabled=%s dest=%s",
            regional,
            item["code"],
            enabled,
            dest_type,
        )
    return inserted


def _ensure_award_achievements_definition(cur, pm_schema: str, regional_schema: str) -> tuple[int | None, bool]:
    """Look up or insert only the award_achievements builtin. Returns (id, inserted)."""
    cur.execute(
        f"""
        SELECT id FROM `{pm_schema}`.`region_report_definitions`
        WHERE schema_name=%s AND code=%s
        """,
        (regional_schema, "award_achievements"),
    )
    row = cur.fetchone()
    if row:
        return int(row["id"]), False
    d = next(x for x in BUILTIN_DEFINITIONS if x["code"] == "award_achievements")
    cur.execute(
        f"""
        INSERT INTO `{pm_schema}`.`region_report_definitions`
          (schema_name, code, name, report_type, is_builtin, is_customized,
           time_window_type)
        VALUES (%s, %s, %s, %s, 1, 0, %s)
        """,
        (
            regional_schema,
            d["code"],
            d["name"],
            d["report_type"],
            d.get("time_window_type"),
        ),
    )
    cur.execute(
        f"""
        SELECT id FROM `{pm_schema}`.`region_report_definitions`
        WHERE schema_name=%s AND code=%s
        """,
        (regional_schema, "award_achievements"),
    )
    created = cur.fetchone()
    if not created:
        return None, False
    return int(created["id"]), True


def backfill_award_achievements_schedules(cur, pm_schema: str) -> dict[str, int]:
    """Create Award Achievements schedules for regions that used the daily EventBridge path.

    For each active region with send_achievements=1 and a non-empty
    achievement_channel that has no award_achievements schedule yet, ensure the
    builtin definition exists and insert a daily 07:00 specific_channels schedule
    targeting that channel. Idempotent on re-run.
    """
    import json

    if not _table_exists(cur, pm_schema, "region_schedules"):
        return {"definitions_ensured": 0, "schedules_inserted": 0, "skipped": 0}

    cur.execute(
        f"""
        SELECT schema_name, region_achievements_channel, send_achievements
        FROM `{pm_schema}`.`region_config`
        WHERE active = 1
          AND COALESCE(send_achievements, 0) = 1
          AND region_achievements_channel IS NOT NULL
          AND region_achievements_channel != ''
        """
    )
    regions = list(cur.fetchall() or [])
    definitions_ensured = 0
    schedules_inserted = 0
    skipped = 0
    for region in regions:
        regional = region.get("schema_name") or ""
        channel = (region.get("region_achievements_channel") or "").strip()
        if not regional or not channel:
            skipped += 1
            continue
        def_id, inserted_def = _ensure_award_achievements_definition(
            cur, pm_schema, regional
        )
        if not def_id:
            skipped += 1
            continue
        if inserted_def:
            definitions_ensured += 1
        cur.execute(
            f"""
            SELECT COUNT(*) AS c FROM `{pm_schema}`.`region_schedules`
            WHERE schema_name=%s AND report_definition_id=%s
            """,
            (regional, def_id),
        )
        if int(cur.fetchone()["c"]) > 0:
            skipped += 1
            continue
        cur.execute(
            f"""
            INSERT INTO `{pm_schema}`.`region_schedules`
              (schema_name, report_definition_id, destination_type, destination_channels,
               frequency_type, time_of_day, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, 0)
            """,
            (
                regional,
                def_id,
                "specific_channels",
                json.dumps([channel]),
                "daily",
                "07:00:00",
            ),
        )
        schedules_inserted += 1
        LOG.info(
            "Backfilled award_achievements schedule schema=%s channel=%s",
            regional,
            channel,
        )
    return {
        "definitions_ensured": definitions_ensured,
        "schedules_inserted": schedules_inserted,
        "skipped": skipped,
    }


def seed_all_regions(cur, pm_schema: str) -> dict[str, int]:
    """Seed builtins + default schedules for every active region. Returns counts.

    The tables and region_config.timezone come from db/migrations, so this
    function creates nothing.
    """
    cur.execute(f"SELECT * FROM `{pm_schema}`.`region_config` WHERE active = 1")
    regions = list(cur.fetchall() or [])
    LOG.info("Active regions in %s.regions: %s", pm_schema, len(regions))
    regions_with_schema = 0
    total_schedules = 0
    for region in regions:
        regional = region.get("schema_name") or ""
        if not regional:
            LOG.info(
                "Skip region=%s — no schema_name", region.get("region")
            )
            continue
        regions_with_schema += 1
        LOG.info(
            "Seeding region=%s schema=%s timezone=%s",
            region.get("region"),
            regional,
            region.get("timezone") or DEFAULT_TIMEZONE,
        )
        inserted = seed_default_schedules(
            cur, pm_schema, region, skip_if_any_schedules=True
        )
        total_schedules += inserted
        LOG.info(
            "Region schema=%s: %s schedule row(s) inserted this run", regional, inserted
        )
    definitions = regions_with_schema * len(BUILTIN_DEFINITIONS)
    LOG.info(
        "Seed summary: regions=%s regions_with_schema=%s definitions_upserted=%s schedules_inserted=%s",
        len(regions),
        regions_with_schema,
        definitions,
        total_schedules,
    )
    return {
        "regions": len(regions),
        "regions_with_schema": regions_with_schema,
        "definitions": definitions,
        "schedules": total_schedules,
    }


def delete_all_definitions_and_schedules(
    cur, pm_schema: str, regional_schema: str
) -> dict[str, int]:
    """Drop every schedule and report definition for a region (FK is RESTRICT)."""
    schedules = delete_all_schedules(cur, pm_schema, regional_schema)
    cur.execute(
        f"DELETE FROM `{pm_schema}`.`region_report_definitions` WHERE schema_name=%s",
        (regional_schema,),
    )
    return {"schedules": schedules, "definitions": int(cur.rowcount or 0)}


def delete_all_definitions_and_schedules(
    cur, pm_schema: str, regional_schema: str
) -> dict[str, int]:
    """Drop every schedule and report definition for a region (FK is RESTRICT)."""
    schedules = delete_all_schedules(cur, pm_schema, regional_schema)
    cur.execute(
        f"DELETE FROM `{pm_schema}`.`region_report_definitions` WHERE schema_name=%s",
        (regional_schema,),
    )
    return {"schedules": schedules, "definitions": int(cur.rowcount or 0)}


def delete_all_schedules(cur, pm_schema: str, regional_schema: str) -> int:
    """Delete all schedule rows for a regional schema. Definitions are kept."""
    cur.execute(
        f"DELETE FROM `{pm_schema}`.`region_schedules` WHERE schema_name=%s",
        (regional_schema,),
    )
    return int(cur.rowcount or 0)


def restore_defaults(cur, pm_schema: str, region: dict[str, Any]) -> int:
    """Upsert builtin definitions and merge/add default schedule rows.

    Customized builtins are left alone (is_customized=1); missing codes and
    non-customized builtins are refreshed from report_defaults.json.
    """
    return seed_default_schedules(cur, pm_schema, region, merge_only=True)


def count_customized_builtins(cur, pm_schema: str, regional_schema: str) -> int:
    cur.execute(
        f"""
        SELECT COUNT(*) AS c FROM `{pm_schema}`.`region_report_definitions`
        WHERE schema_name=%s AND is_builtin=1 AND is_customized=1
        """,
        (regional_schema,),
    )
    return int(cur.fetchone()["c"])


def count_schedules_for_definition(cur, pm_schema: str, definition_id: int) -> int:
    cur.execute(
        f"SELECT COUNT(*) AS c FROM `{pm_schema}`.`region_schedules` WHERE report_definition_id=%s",
        (definition_id,),
    )
    return int(cur.fetchone()["c"])


def delete_definition_and_schedules(
    cur, pm_schema: str, definition_id: int, regional_schema: str
) -> dict[str, int]:
    """Delete schedule rows for a definition, then the definition itself."""
    cur.execute(
        f"""
        DELETE FROM `{pm_schema}`.`region_schedules`
        WHERE report_definition_id=%s AND schema_name=%s
        """,
        (definition_id, regional_schema),
    )
    schedules = int(cur.rowcount or 0)
    cur.execute(
        f"""
        DELETE FROM `{pm_schema}`.`region_report_definitions`
        WHERE id=%s AND schema_name=%s
        """,
        (definition_id, regional_schema),
    )
    definitions = int(cur.rowcount or 0)
    return {"schedules": schedules, "definitions": definitions}


def uniquify_definition_code(
    cur, pm_schema: str, regional_schema: str, base_code: str
) -> str:
    """Return base_code, or base_code_copy / base_code_copy_N if taken."""
    candidate = f"{base_code}_copy"
    n = 2
    while True:
        cur.execute(
            f"""
            SELECT COUNT(*) AS c FROM `{pm_schema}`.`region_report_definitions`
            WHERE schema_name=%s AND code=%s
            """,
            (regional_schema, candidate),
        )
        if int(cur.fetchone()["c"]) == 0:
            return candidate
        candidate = f"{base_code}_copy_{n}"
        n += 1


def duplicate_definition(
    cur, pm_schema: str, regional_schema: str, source: dict[str, Any]
) -> dict[str, Any]:
    """Copy a definition with uniquified code, (copy) name, is_builtin=0."""
    new_code = uniquify_definition_code(cur, pm_schema, regional_schema, source["code"])
    new_name = f"{source.get('name') or source['code']} (copy)"
    fields = source.get("fields")
    if fields is not None and not isinstance(fields, str):
        import json

        fields = json.dumps(fields)
    cur.execute(
        f"""
        INSERT INTO `{pm_schema}`.`region_report_definitions`
          (schema_name, code, name, report_type, is_builtin, is_customized,
           kind, source, fields, metric, aggregation, group_by, top_n,
           time_window_type, window_days, window_start, window_end)
        VALUES (%s,%s,%s,%s,0,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            regional_schema,
            new_code,
            new_name,
            source.get("report_type") or "custom_report",
            source.get("kind"),
            source.get("source"),
            fields,
            source.get("metric"),
            source.get("aggregation"),
            source.get("group_by"),
            source.get("top_n"),
            source.get("time_window_type"),
            source.get("window_days"),
            source.get("window_start"),
            source.get("window_end"),
        ),
    )
    cur.execute(
        f"""
        SELECT * FROM `{pm_schema}`.`region_report_definitions`
        WHERE schema_name=%s AND code=%s
        """,
        (regional_schema, new_code),
    )
    return cur.fetchone()
