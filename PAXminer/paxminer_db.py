"""Shared MySQL connection helpers for PAXminer (Lambda / TiDB-style env vars)."""
from __future__ import annotations

import logging
import os
import ssl
from typing import Any

import pymysql

LOG = logging.getLogger(__name__)


def connect_mysql(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    tls: bool = False,
):
    kw: dict = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "db": database,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if tls:
        kw["ssl"] = ssl.create_default_context()
    return pymysql.connect(**kw)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def connect_from_env(database: str):
    """Connect using Lambda / TiDB-style env vars (same names as slackblast)."""
    host = os.environ.get("DATABASE_HOST") or os.environ.get("host")
    user = os.environ.get("DATABASE_USER") or os.environ.get("user")
    password = os.environ.get("DATABASE_PASSWORD") or os.environ.get("password")
    if not host or not user or password is None:
        raise OSError(
            "DATABASE_HOST, DATABASE_USER, and DATABASE_PASSWORD (or legacy host, user, password) must be set"
        )
    port = int(os.environ.get("DATABASE_PORT", os.environ.get("port", "3306")))
    tls = _env_bool("DATABASE_TLS_ENABLED", True)
    logging.getLogger(__name__).info(
        "connect_from_env: database=%s host=%s port=%s tls=%s",
        database,
        host,
        port,
        tls,
    )
    return connect_mysql(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        tls=tls,
    )


def paxminer_schema_from_env() -> str:
    return os.environ.get("PAXMINER_SCHEMA", "paxminer").strip() or "paxminer"


def read_sql_df(conn, sql: str, params: Any = None):
    """Load a SQL result into a DataFrame via an explicit *tuple* cursor.

    Never pass a DictCursor connection to ``pd.read_sql``: under pandas 3.x,
    ``lib.to_object_array_tuples`` iterates dicts by key, so every cell becomes
    the column name string (e.g. date column filled with ``"date"``). That
    silently empties Kotter / achievements / custom reports after
    ``to_datetime(..., errors="coerce")``.

    Pandas is imported lazily so lightweight Slack Lambda images (no pandas)
    can still import this module for ``connect_from_env``.
    """
    import pandas as pd

    with conn.cursor(pymysql.cursors.Cursor) as cur:
        cur.execute(sql, params or ())
        cols = [d[0] for d in (cur.description or [])]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)
