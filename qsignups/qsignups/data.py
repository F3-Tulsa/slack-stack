"""Same-schema reads of regional aos and beatdowns.

QSignups connects to DATABASE_SCHEMA, which holds those tables. The SQL does
not qualify another schema.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from sqlalchemy import text

_SCHEMA = re.compile(r"^[a-z0-9_]+$")


def database_schema() -> str:
    schema = (os.environ.get("DATABASE_SCHEMA") or "").strip()
    if not _SCHEMA.fullmatch(schema):
        raise RuntimeError(f"DATABASE_SCHEMA {schema!r} must match ^[a-z0-9_]+$")
    return schema


def site_q_user_id(conn, channel_id: str) -> Optional[str]:
    row = conn.execute(
        text("SELECT site_q_user_id FROM aos WHERE channel_id = :ch LIMIT 1"),
        {"ch": channel_id},
    ).first()
    if row is None:
        return None
    val = row[0]
    return val if val else None


def aoq_channel_ids(conn, user_id: str) -> list[str]:
    rows = conn.execute(
        text("SELECT channel_id FROM aos WHERE site_q_user_id = :uid"),
        {"uid": user_id},
    ).fetchall()
    return [r[0] for r in rows if r and r[0]]


def user_has_q_history(conn, user_id: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM beatdowns WHERE q_user_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).first()
    return row is not None
