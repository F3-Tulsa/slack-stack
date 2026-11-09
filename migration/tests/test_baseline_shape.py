"""The rehearsed baseline shape: parser, diff, and the conversion statements."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "migration"))
sys.path.insert(0, str(_REPO / "db"))

from baseline_shape import (  # noqa: E402
    BASELINE,
    CONVERSION_SQL,
    differences,
    parse_baseline,
)
from convert_to_baseline import guard, scratch_name  # noqa: E402
from migrate import MigrationError  # noqa: E402


def test_baseline_parses_every_table():
    tables = parse_baseline(BASELINE.read_text(encoding="utf-8"))
    assert len(tables) == 21
    weekly = tables["qsignups_weekly"]
    by_name = {col["name"]: col for col in weekly["columns"]}
    assert by_name["ao_channel_id"]["type"] == "varchar(32)"
    assert by_name["ao_channel_id"]["collation"] == "utf8mb4_bin"
    assert by_name["event_day_of_week"]["type"] == "varchar(16)"
    assert by_name["event_day_of_week"]["collation"] == "utf8mb4_unicode_ci"
    indexes = {item["name"]: item for item in weekly["indexes"]}
    assert indexes["weekly_idx"]["columns"] == [
        "ao_channel_id",
        "event_day_of_week",
        "event_time",
        "team_id",
    ]


def test_differences_flag_collation_width_index_and_extra_column():
    expected = {
        "users": {
            "columns": [
                {
                    "name": "user_id",
                    "type": "varchar(45)",
                    "nullable": False,
                    "default": None,
                    "collation": "utf8mb4_bin",
                }
            ],
            "indexes": [{"name": "PRIMARY", "unique": True, "columns": ["user_id"]}],
        }
    }
    live = {
        "users": {
            "columns": [
                {
                    "name": "user_id",
                    "type": "varchar(255)",
                    "nullable": False,
                    "default": None,
                    "collation": "utf8mb4_unicode_ci",
                }
            ],
            "indexes": [{"name": "PRIMARY", "unique": True, "columns": ["user_name"]}],
        },
        "extra": {"columns": [], "indexes": []},
    }
    found = differences(live, expected)
    assert "users.user_id type is 'varchar(255)', baseline has 'varchar(45)'" in found
    assert "users.user_id collation is 'utf8mb4_unicode_ci', baseline has 'utf8mb4_bin'" in found
    assert "users.PRIMARY columns differ" in found
    assert "extra table extra" in found


def test_differences_flag_auto_increment_table_collation_and_views():
    expected = {
        "qsignups_features": {
            "collation": "utf8mb4_bin",
            "columns": [
                {
                    "name": "id",
                    "type": "int",
                    "nullable": False,
                    "default": None,
                    "collation": "",
                    "auto_increment": True,
                }
            ],
            "indexes": [],
        }
    }
    live = {
        "qsignups_features": {
            "collation": "utf8mb4_0900_ai_ci",
            "columns": [
                {
                    "name": "id",
                    "type": "int",
                    "nullable": False,
                    "default": None,
                    "collation": "",
                    "auto_increment": False,
                }
            ],
            "indexes": [],
        }
    }
    found = differences(live, expected, live_views=set(), expected_views={"vw_aos_sort"})
    assert any("auto_increment" in item for item in found)
    assert any("table collation" in item for item in found)
    assert "missing view vw_aos_sort" in found


def test_conversion_recreates_weekly_idx_after_convert():
    text = "\n".join(CONVERSION_SQL)
    assert text.index("qsignups_weekly CONVERT") < text.index("ADD UNIQUE KEY weekly_idx")
    assert "VARCHAR(32)" in text
    assert "utf8mb4_unicode_ci" in text


def test_convert_refuses_prod_writes(tmp_path: Path):
    path = tmp_path / ".env.migration.prod"
    path.write_text(
        "F3_REGION_NAME=f3ttown\nTARGET_HOST=h\nTARGET_USER=u\nTARGET_PASSWORD=p\n",
        encoding="utf-8",
    )
    with pytest.raises(MigrationError, match="refusing to convert"):
        guard(path, write=True)
    schema, _settings = guard(path, write=False)
    assert schema == "f3ttown_prod"


def test_scratch_name_is_unique_and_keeps_the_stage():
    first = scratch_name("f3ttown_prod")
    second = scratch_name("f3ttown_prod")
    assert first.startswith("compare_scratch_")
    assert first.endswith("_prod")
    assert first != second
    assert scratch_name("citest_retry").endswith("_test")
