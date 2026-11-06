"""Forward-only numbered SQL runner.

Files live in ``db/migrations/NNNN_slug.sql``. The runner creates
``schema_migrations`` itself, applies each pending file, and records the
file only after every statement succeeds. It does not know about prod
deploys: ``deploy.sh`` and ``deploy.yml`` do not call it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MIGRATION_FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
SCHEMA_NAME = re.compile(r"^[a-z0-9]+_(test|rehearsal|prod)$")
REGION_PREFIX = re.compile(r"^[a-z0-9]+$")

REFUSED_PREFIXES = ("f3scissortail_", "weaselbot_")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


class MigrationError(RuntimeError):
    """A file, a recorded checksum, or a statement failed."""


def guard_schema(schema: str, *, allow_prod: bool) -> None:
    """Refuse names this branch must not migrate."""
    if not SCHEMA_NAME.fullmatch(schema):
        raise MigrationError(
            f"schema {schema!r} must look like <region>_<test|rehearsal|prod> "
            "with a lowercase region name"
        )
    region = schema.rsplit("_", 1)[0]
    if not REGION_PREFIX.fullmatch(region):
        raise MigrationError(f"region {region!r} must match ^[a-z0-9]+$")
    if schema.startswith(REFUSED_PREFIXES):
        raise MigrationError(f"schema {schema!r} is outside this consolidation")
    if schema.endswith("_prod") and not allow_prod:
        raise MigrationError(
            f"refusing {schema!r}: pass --allow-prod to migrate a prod schema"
        )


def discover(directory: Path) -> list[Migration]:
    """Return migrations in version order. Reject gaps and duplicate numbers."""
    if not directory.is_dir():
        raise MigrationError(f"migrations directory not found: {directory}")
    found: dict[int, Migration] = {}
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix != ".sql" and not path.is_file():
            continue
        match = MIGRATION_FILE.fullmatch(path.name)
        if match is None:
            if path.suffix == ".sql":
                raise MigrationError(
                    f"{path.name} must be NNNN_slug.sql with a lowercase slug"
                )
            continue
        version = int(match.group(1))
        if version in found:
            raise MigrationError(f"duplicate migration number {version:04d}")
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        found[version] = Migration(version, match.group(2), path, checksum, sql)
    versions = sorted(found)
    if versions:
        expected = list(range(1, versions[-1] + 1))
        if versions != expected:
            missing = [f"{n:04d}" for n in expected if n not in found]
            raise MigrationError(f"migration numbers have gaps: {', '.join(missing)}")
    return [found[n] for n in versions]


def split_sql(text: str) -> list[str]:
    """Split a script on semicolons that are not inside quotes or comments."""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    in_single = False
    in_double = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if not in_single and not in_double and ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        if not in_single and not in_double and ch == "-" and nxt == "-":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end + 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue
        if ch == ";" and not in_single and not in_double:
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _applied(cursor) -> dict[int, str]:
    cursor.execute("SELECT version, checksum FROM schema_migrations")
    rows = cursor.fetchall()
    return {int(row["version"]): row["checksum"] for row in rows}


def ensure_bookkeeping(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INT NOT NULL,
            name VARCHAR(255) NOT NULL,
            checksum CHAR(64) NOT NULL,
            applied_at DATETIME NOT NULL,
            PRIMARY KEY (version)
        ) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def apply_pending(cursor, migrations: list[Migration], *, to: int | None = None) -> list[int]:
    """Apply files whose version is not recorded. Return the versions applied."""
    applied = _applied(cursor)
    done: list[int] = []
    for migration in migrations:
        if to is not None and migration.version > to:
            break
        recorded = applied.get(migration.version)
        if recorded is not None:
            if recorded != migration.checksum:
                raise MigrationError(
                    f"{migration.version:04d}_{migration.name} checksum changed "
                    f"after it was applied ({recorded} != {migration.checksum})"
                )
            continue
        for statement in split_sql(migration.sql):
            try:
                cursor.execute(statement)
            except Exception as exc:
                raise MigrationError(
                    f"{migration.version:04d}_{migration.name} failed on: {statement}"
                ) from exc
        cursor.execute(
            """
            INSERT INTO schema_migrations (version, name, checksum, applied_at)
            VALUES (%s, %s, %s, %s)
            """,
            (
                migration.version,
                migration.name,
                migration.checksum,
                datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        )
        done.append(migration.version)
    return done


def connect_from_env():
    """Connect with DATABASE_* or, failing that, the migration TARGET_* vars."""
    import pymysql

    host = os.environ.get("DATABASE_HOST") or os.environ.get("TARGET_HOST")
    user = os.environ.get("DATABASE_USER") or os.environ.get("TARGET_USER")
    password = os.environ.get("DATABASE_PASSWORD") or os.environ.get("TARGET_PASSWORD")
    if not host or not user or password is None:
        raise MigrationError("DATABASE_HOST, DATABASE_USER, and DATABASE_PASSWORD are required")
    port = int(os.environ.get("DATABASE_PORT") or os.environ.get("TARGET_PORT") or "4000")
    tls_raw = os.environ.get("DATABASE_TLS_ENABLED", os.environ.get("TARGET_TLS_ENABLED", "true"))
    tls = tls_raw.lower() in ("1", "true", "yes")
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        ssl={"ssl": {}} if tls else None,
        autocommit=True,
    )


def run(schema: str, directory: Path, *, to: int | None, allow_prod: bool) -> list[int]:
    guard_schema(schema, allow_prod=allow_prod)
    migrations = discover(directory)
    conn = connect_from_env()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{schema}`")
            cursor.execute(f"USE `{schema}`")
            ensure_bookkeeping(cursor)
            return apply_pending(cursor, migrations, to=to)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply pending numbered SQL files")
    parser.add_argument("--schema", required=True, help="Target schema, e.g. f3ttown_test")
    parser.add_argument(
        "--migrations",
        type=Path,
        default=Path(__file__).resolve().parent / "migrations",
    )
    parser.add_argument("--to", type=int, default=None, help="Apply through this version")
    parser.add_argument(
        "--allow-prod",
        action="store_true",
        help="Required when --schema ends in _prod",
    )
    args = parser.parse_args(argv)
    try:
        applied = run(args.schema, args.migrations, to=args.to, allow_prod=args.allow_prod)
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if applied:
        print("applied " + ", ".join(f"{n:04d}" for n in applied))
    else:
        print("no pending migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
