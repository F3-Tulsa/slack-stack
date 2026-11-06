"""Same-schema reads and writes for the one region database.

The connection is already ``DATABASE_SCHEMA``. These queries do not name a
second schema.
"""

from __future__ import annotations

import os
import re

_SCHEMA = re.compile(r"^[a-z0-9_]+$")

REGION_TABLE = "region_config"
ACHIEVEMENT_CHANNEL = "region_achievements_channel"


def database_schema() -> str:
    """The only schema this process may open. Deploy sets it; nothing derives it."""
    schema = (os.environ.get("DATABASE_SCHEMA") or "").strip()
    if not _SCHEMA.fullmatch(schema):
        raise RuntimeError(f"DATABASE_SCHEMA {schema!r} must match ^[a-z0-9_]+$")
    return schema


def region_for_team(cur, team_id: str) -> dict | None:
    cur.execute(
        f"SELECT * FROM `{REGION_TABLE}` WHERE team_id=%s LIMIT 1",
        (team_id,),
    )
    return cur.fetchone()


def custom_fields_row(cur, *, team_id: str | None, schema_name: str | None) -> dict:
    if team_id:
        cur.execute(
            f"SELECT custom_fields FROM `{REGION_TABLE}` WHERE team_id=%s LIMIT 1",
            (team_id,),
        )
    else:
        cur.execute(
            f"SELECT custom_fields FROM `{REGION_TABLE}` WHERE schema_name=%s LIMIT 1",
            (schema_name,),
        )
    return cur.fetchone() or {}
