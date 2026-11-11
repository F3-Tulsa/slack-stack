"""Shape of 0001_baseline.sql, and how a live schema differs from it.

The conversion statements are the ones that succeeded on the rehearsal copy.
TiDB error 8200 rejects a collation change on an indexed column, so the
unique indexes are dropped first and put back after the column changes.
"""

from __future__ import annotations

import re
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[1] / "db" / "migrations" / "0001_baseline.sql"
QSIGNUPS_TABLES = (
    "qsignups_aos",
    "qsignups_features",
    "qsignups_master",
    "qsignups_regions",
    "qsignups_weekly",
)


def secondary_indexes(cursor, schema: str, tables: tuple[str, ...]) -> list[tuple[str, str]]:
    """Non-primary indexes. TiDB rejects a collation change while one of these remains."""
    cursor.execute(
        """
        SELECT TABLE_NAME AS table_name, INDEX_NAME AS index_name
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN %s AND INDEX_NAME <> 'PRIMARY'
        GROUP BY TABLE_NAME, INDEX_NAME
        ORDER BY TABLE_NAME, INDEX_NAME
        """,
        (schema, tables),
    )
    return [(row["table_name"], row["index_name"]) for row in cursor.fetchall()]

# The sequence that succeeded on f3ttown_rehearsal. A CONVERT while these
# indexes exist fails with TiDB 8200.
CONVERSION_SQL = (
    "ALTER TABLE qsignups_weekly "
    "MODIFY ao_channel_id VARCHAR(32) CHARACTER SET utf8 COLLATE utf8_general_ci NOT NULL, "
    "MODIFY event_day_of_week VARCHAR(16) CHARACTER SET utf8 COLLATE utf8_general_ci NOT NULL, "
    "MODIFY event_time VARCHAR(16) CHARACTER SET utf8 COLLATE utf8_general_ci NOT NULL, "
    "MODIFY team_id VARCHAR(32) CHARACTER SET utf8 COLLATE utf8_general_ci NOT NULL",
    "ALTER TABLE qsignups_aos CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
    "ALTER TABLE qsignups_features CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
    "ALTER TABLE qsignups_master CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
    "ALTER TABLE qsignups_regions CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
    "ALTER TABLE qsignups_weekly CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
    "ALTER TABLE qsignups_aos "
    "MODIFY ao_display_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY ao_location_subtitle VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY current_month_weinke LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
    "ALTER TABLE qsignups_master "
    "MODIFY event_time VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY event_end_time VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY event_day_of_week VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY event_type VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY event_special VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY q_pax_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
    "ALTER TABLE qsignups_regions "
    "MODIFY current_week_weinke LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY next_week_weinke LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY workspace_name VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY current_week_weinke_updated VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY next_week_weinke_updated VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY timezone VARCHAR(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
    "ALTER TABLE qsignups_weekly "
    "MODIFY event_day_of_week VARCHAR(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY event_time VARCHAR(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY event_end_time VARCHAR(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY event_type VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL",
    "ALTER TABLE users "
    "MODIFY user_name VARCHAR(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY real_name VARCHAR(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY phone VARCHAR(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY email VARCHAR(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
    "ALTER TABLE aos MODIFY ao VARCHAR(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL",
    "ALTER TABLE achievements_list "
    "MODIFY name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY description VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, "
    "MODIFY verb VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL",
    "ALTER TABLE beatdowns "
    "MODIFY backblast LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY backblast_parsed LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY fngs VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY activity_type VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
    "ALTER TABLE slack_bots "
    "MODIFY enterprise_name VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY team_name VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
    "ALTER TABLE slack_installations "
    "MODIFY enterprise_name VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL, "
    "MODIFY team_name VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL",
    "ALTER TABLE qsignups_aos ADD UNIQUE KEY aos_idx (ao_channel_id, team_id)",
    "ALTER TABLE qsignups_master ADD UNIQUE KEY master_idx (ao_channel_id, event_date, event_time, team_id)",
    "ALTER TABLE qsignups_regions ADD UNIQUE KEY region_idx (team_id)",
    "ALTER TABLE qsignups_weekly ADD UNIQUE KEY weekly_idx "
    "(ao_channel_id, event_day_of_week, event_time, team_id)",
    "ALTER TABLE qsignups_features ADD KEY region_id_fk (region_id)",
    "ALTER TABLE achievement_versions MODIFY range_mode varchar(24) "
    "COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER effective_to",
)

_COLUMN = re.compile(
    r"^`(?P<name>[^`]+)`\s+(?P<type>[a-z]+(?:\(\d+\))?)"
    r"(?:\s+COLLATE\s+(?P<collation>[a-z0-9_]+))?"
    r"(?:\s+(?P<nullability>NOT NULL|NULL))?"
    r"(?:\s+DEFAULT\s+(?P<default>CURRENT_TIMESTAMP|NULL|'(?:[^']|\\')*'))?"
    r"(?:\s+ON UPDATE\s+CURRENT_TIMESTAMP)?"
    r"(?P<auto>\s+AUTO_INCREMENT)?$",
    re.IGNORECASE,
)
_INDEX = re.compile(
    r"^(?:PRIMARY KEY|(?P<unique>UNIQUE )?KEY(?:\s+`(?P<name>[^`]+)`)?)\s*\((?P<cols>[^)]*)\)",
    re.IGNORECASE,
)
_INT_WIDTH = re.compile(r"\b(tinyint|smallint|mediumint|int|bigint)\(\d+\)")


def parse_views(sql: str) -> set[str]:
    """View names in 0001. The compare checks that each one exists."""
    return set(re.findall(r"CREATE OR REPLACE SQL SECURITY INVOKER VIEW `([^`]+)`", sql))


def parse_baseline(sql: str) -> dict[str, dict]:
    """Tables in 0001, keyed by name."""
    tables: dict[str, dict] = {}
    for statement in _statements(sql):
        match = re.match(r"CREATE TABLE IF NOT EXISTS `([^`]+)` \(", statement)
        if not match:
            continue
        name = match.group(1)
        body, _, tail = statement.partition("\n) ENGINE=")
        body = body.split("(", 1)[1]
        charset = re.search(r"CHARSET=(\w+)", tail)
        collation = re.search(r"COLLATE=(\w+)", tail)
        table_collation = collation.group(1) if collation else ""
        columns = []
        indexes = []
        for raw in body.splitlines():
            line = raw.strip().rstrip(",")
            if not line:
                continue
            if line.startswith("`"):
                columns.append(_column(line, table_collation))
            else:
                indexes.append(_index(line))
        tables[name] = {
            "charset": charset.group(1) if charset else "",
            "collation": (table_collation or "").lower(),
            "columns": columns,
            "indexes": indexes,
        }
    return tables


def differences(
    live: dict[str, dict],
    expected: dict[str, dict],
    *,
    live_views: set[str] | None = None,
    expected_views: set[str] | None = None,
) -> list[str]:
    """Names of shape differences. ``schema_migrations`` is the runner's table."""
    problems = []
    if live_views is not None and expected_views is not None:
        for name in sorted(expected_views - live_views):
            problems.append(f"missing view {name}")
        for name in sorted(live_views - expected_views):
            problems.append(f"extra view {name}")
    live_names = set(live) - {"schema_migrations"}
    for name in sorted(set(expected) - live_names):
        problems.append(f"missing table {name}")
    for name in sorted(live_names - set(expected)):
        problems.append(f"extra table {name}")
    for name in sorted(set(expected) & live_names):
        problems.extend(_table_diff(name, live[name], expected[name]))
    return problems


def fetch_live(cursor, schema: str) -> dict[str, dict]:
    """Column and index shape of one schema, from information_schema."""
    cursor.execute(
        """
        SELECT TABLE_NAME AS table_name, TABLE_COLLATION AS table_collation
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'
        """,
        (schema,),
    )
    tables = list(cursor.fetchall())
    names = [row["table_name"] for row in tables]
    collations = {row["table_name"]: (row["table_collation"] or "").lower() for row in tables}
    live = {}
    for name in names:
        cursor.execute(
            """
            SELECT COLUMN_NAME AS name, COLUMN_TYPE AS column_type, IS_NULLABLE AS nullable,
                   COLUMN_DEFAULT AS column_default, COLLATION_NAME AS collation,
                   EXTRA AS extra
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            ORDER BY ORDINAL_POSITION
            """,
            (schema, name),
        )
        columns = [
            {
                "name": row["name"],
                "type": normalize_type(row["column_type"]),
                "nullable": row["nullable"] == "YES",
                "default": normalize_default(row["column_default"]),
                "collation": (row["collation"] or "").lower(),
                "auto_increment": "auto_increment" in (row["extra"] or "").lower(),
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT INDEX_NAME AS name, NON_UNIQUE AS non_unique, COLUMN_NAME AS column_name
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """,
            (schema, name),
        )
        indexes: dict[str, dict] = {}
        for row in cursor.fetchall():
            item = indexes.setdefault(
                row["name"],
                {"name": row["name"], "unique": int(row["non_unique"]) == 0, "columns": []},
            )
            item["columns"].append(row["column_name"])
        live[name] = {
            "columns": columns,
            "indexes": list(indexes.values()),
            "collation": collations.get(name, ""),
        }
    return live


def fetch_views(cursor, schema: str) -> set[str]:
    cursor.execute(
        """
        SELECT TABLE_NAME AS table_name
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='VIEW'
        """,
        (schema,),
    )
    return {row["table_name"] for row in cursor.fetchall()}


def normalize_type(column_type: str) -> str:
    text = (column_type or "").lower().strip()
    return _INT_WIDTH.sub(r"\1", text)


def normalize_default(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        text = text[1:-1]
    lowered = text.lower().replace(" ", "")
    if lowered in ("current_timestamp", "current_timestamp()"):
        return "current_timestamp"
    return text


def _statements(sql: str) -> list[str]:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "db"))
    from migrate import split_sql

    return split_sql(sql)


def _column(line: str, table_collation: str) -> dict:
    match = _COLUMN.match(line)
    if not match:
        raise ValueError(f"cannot parse column: {line}")
    default = match.group("default")
    if default is not None and default.upper() == "NULL":
        default = None
    column_type = normalize_type(match.group("type"))
    text = column_type.startswith(("char", "varchar", "tinytext", "text", "mediumtext", "longtext"))
    collation = match.group("collation") or (table_collation if text else "")
    return {
        "name": match.group("name"),
        "type": column_type,
        "nullable": (match.group("nullability") or "").upper() != "NOT NULL",
        "default": normalize_default(default),
        "collation": collation.lower(),
        "auto_increment": bool(match.group("auto")),
    }


def _index(line: str) -> dict:
    match = _INDEX.match(line)
    if not match:
        raise ValueError(f"cannot parse index: {line}")
    name = match.group("name") or "PRIMARY"
    columns = [part.strip().strip("`") for part in match.group("cols").split(",")]
    return {"name": name, "unique": bool(match.group("unique")) or name == "PRIMARY", "columns": columns}


def _table_diff(name: str, live: dict, expected: dict) -> list[str]:
    problems = []
    live_cols = live["columns"]
    expected_cols = expected["columns"]
    if [col["name"] for col in live_cols] != [col["name"] for col in expected_cols]:
        problems.append(f"{name} columns differ")
        return problems
    for got, want in zip(live_cols, expected_cols):
        for field in ("type", "nullable", "default", "collation"):
            if got.get(field) != want.get(field):
                problems.append(
                    f"{name}.{got['name']} {field} is {got.get(field)!r}, baseline has {want.get(field)!r}"
                )
        if bool(got.get("auto_increment")) != bool(want.get("auto_increment")):
            problems.append(
                f"{name}.{got['name']} auto_increment is {bool(got.get('auto_increment'))}, "
                f"baseline has {bool(want.get('auto_increment'))}"
            )
    if (live.get("collation") or "") != (expected.get("collation") or ""):
        problems.append(
            f"{name} table collation is {live.get('collation')!r}, "
            f"baseline has {expected.get('collation')!r}"
        )
    live_idx = {item["name"]: item for item in live["indexes"]}
    expected_idx = {item["name"]: item for item in expected["indexes"]}
    for index in sorted(set(expected_idx) - set(live_idx)):
        problems.append(f"{name} missing index {index}")
    for index in sorted(set(live_idx) - set(expected_idx)):
        problems.append(f"{name} extra index {index}")
    for index in sorted(set(expected_idx) & set(live_idx)):
        if live_idx[index]["columns"] != expected_idx[index]["columns"]:
            problems.append(f"{name}.{index} columns differ")
        if live_idx[index]["unique"] != expected_idx[index]["unique"]:
            problems.append(f"{name}.{index} uniqueness differs")
    return problems
