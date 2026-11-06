"""The one schema Slackblast reads and writes."""

from __future__ import annotations

import os
import re

_SCHEMA = re.compile(r"^[a-z0-9_]+$")


def database_schema() -> str:
    """Deploy sets DATABASE_SCHEMA. Callers do not pick another schema."""
    schema = (os.environ.get("DATABASE_SCHEMA") or "").strip()
    if not _SCHEMA.fullmatch(schema):
        raise RuntimeError(f"DATABASE_SCHEMA {schema!r} must match ^[a-z0-9_]+$")
    return schema
