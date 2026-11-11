"""0001 creates everything the retired runtime DDL copies created.

PAXMiner used to create its achievements and scheduler tables at runtime and
add columns on the fly. Those copies now live in
migration/paxminer_phases/legacy_ddl.py as Tulsa history, and db/migrations is
the only source for a region's schema. These tests fail if 0001 stops covering
a table, column, view or key that the copies created.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "migration"))
sys.path.insert(0, str(_REPO / "PAXminer"))

from baseline_shape import BASELINE, parse_baseline, parse_views  # noqa: E402
from paxminer_phases import legacy_ddl  # noqa: E402

COPIED_TABLES = {
    "achievements_list": legacy_ddl.ACHIEVEMENTS_LIST_DDL,
    "achievements_awarded": legacy_ddl.ACHIEVEMENTS_AWARDED_DDL,
    "achievement_versions": legacy_ddl.ACHIEVEMENT_VERSIONS_DDL,
    "region_report_definitions": legacy_ddl.DDL_REGION_REPORT_DEFINITIONS,
    "region_schedules": legacy_ddl.DDL_REGION_SCHEDULES,
}

# Views the copies created: achievements_view in achievement_rules.py and
# attendance_view in scripts/seed_test_region.py.
COPIED_VIEWS = {"achievements_view", "attendance_view"}

# Columns the retired ensure_* helpers added at runtime
# (schedule_schema.py and achievements/range.py).
RUNTIME_ADDED_COLUMNS = {
    "region_config": ("timezone", "log_channel"),
    "region_report_definitions": ("is_customized", "enabled"),
    "region_schedules": ("last_run_at",),
    "achievement_versions": ("range_mode",),
    "achievements_list": ("reeval_queued_at", "emoji"),
}

# Keys the copies declared that no numbered file adds, as (table, columns, unique).
# 0003 adds UNIQUE code and KEY pax_id. KEY enabled stays out: the table is tiny.
# A new gap fails here.
COPY_ONLY_KEYS = {
    ("achievements_list", ("enabled",), False),
}

_ALTER_TABLE = re.compile(r"ALTER\s+TABLE\s+`?(\w+)`?", re.IGNORECASE)
_ADDED_KEY = re.compile(
    r"ADD\s+(UNIQUE\s+)?KEY\s+`\w+`\s*\(([^)]*)\)",
    re.IGNORECASE,
)

_COPY_COLUMN = re.compile(r"^\s*`(\w+)`\s", re.MULTILINE)
_COPY_KEY = re.compile(
    r"^\s*(PRIMARY KEY|UNIQUE KEY `\w+`|KEY `\w+`)\s*\(([^)]*)\)", re.MULTILINE
)


def _baseline() -> dict[str, dict]:
    return parse_baseline(BASELINE.read_text(encoding="utf-8"))


def _copy_keys(ddl: str) -> set[tuple[tuple[str, ...], bool]]:
    keys = set()
    for kind, cols in _COPY_KEY.findall(ddl):
        columns = tuple(part.strip().strip("`") for part in cols.split(","))
        keys.add((columns, not kind.startswith("KEY")))
    return keys


def test_baseline_has_every_copied_table_and_column():
    baseline = _baseline()
    for table, ddl in COPIED_TABLES.items():
        assert table in baseline, table
        have = {col["name"] for col in baseline[table]["columns"]}
        missing = set(_COPY_COLUMN.findall(ddl)) - have
        assert not missing, f"{table} lacks {sorted(missing)}"


def test_baseline_has_every_runtime_added_column():
    baseline = _baseline()
    for table, columns in RUNTIME_ADDED_COLUMNS.items():
        have = {col["name"] for col in baseline[table]["columns"]}
        assert set(columns) <= have, f"{table} lacks {sorted(set(columns) - have)}"


def test_baseline_has_the_copied_views():
    views = parse_views(BASELINE.read_text(encoding="utf-8"))
    assert COPIED_VIEWS <= views


def _keys_added_after_baseline() -> set[tuple[str, tuple[str, ...], bool]]:
    """Keys later numbered files add. 0001 itself has no ALTER TABLE."""
    keys: set[tuple[str, tuple[str, ...], bool]] = set()
    for path in sorted(BASELINE.parent.glob("*.sql")):
        if path.name.startswith("0001"):
            continue
        for statement in path.read_text(encoding="utf-8").split(";"):
            table = _ALTER_TABLE.search(statement)
            if not table:
                continue
            for unique, cols in _ADDED_KEY.findall(statement):
                columns = tuple(part.strip().strip("`") for part in cols.split(","))
                keys.add((table.group(1), columns, bool(unique.strip())))
    return keys


def test_only_known_copy_keys_are_missing_from_the_migrations():
    baseline = _baseline()
    uncovered = set()
    for table, ddl in COPIED_TABLES.items():
        indexes = baseline[table]["indexes"]
        for columns, unique in _copy_keys(ddl):
            covered = any(
                tuple(index["columns"]) == columns and (index["unique"] or not unique)
                for index in indexes
            )
            if not covered:
                uncovered.add((table, columns, unique))
    added = _keys_added_after_baseline()
    assert ("achievements_list", ("code",), True) in added
    assert ("achievements_awarded", ("pax_id",), False) in added
    assert ("achievements_list", ("enabled",), False) not in added
    assert uncovered - added == COPY_ONLY_KEYS


def test_app_relies_on_baseline_unique_keys():
    """INSERT IGNORE and upserts depend on these keys, so 0001 must keep them."""
    baseline = _baseline()
    expected = {
        "achievements_awarded": ("achievement_id", "pax_id", "period_key"),
        "achievement_versions": ("version_key",),
        "region_report_definitions": ("schema_name", "code"),
    }
    for table, columns in expected.items():
        assert any(
            index["unique"] and tuple(index["columns"]) == columns
            for index in baseline[table]["indexes"]
        ), f"{table} lost unique {columns}"
