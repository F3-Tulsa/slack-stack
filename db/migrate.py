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
REGION_NAME = re.compile(r"^[a-z0-9]+$")
STAGES = ("test", "rehearsal", "prod")
APP_REGION_NAMES = frozenset({"paxminer", "slackblast", "qsignups", "weaselbot"})
PREFIXES = ("DATABASE", "TARGET")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


class MigrationError(RuntimeError):
    """A file, a recorded checksum, or a statement failed."""


def derived_schema(region: str, stage: str) -> str:
    """Schema name is ``${F3_REGION_NAME}_<stage>``. App names are not regions."""
    if stage not in STAGES:
        raise MigrationError(f"stage {stage!r} must be one of {', '.join(STAGES)}")
    if not REGION_NAME.fullmatch(region or ""):
        raise MigrationError(f"F3_REGION_NAME {region!r} must match ^[a-z0-9]+$")
    if region in APP_REGION_NAMES:
        raise MigrationError(f"F3_REGION_NAME {region!r} is an app schema, not a region")
    return f"{region}_{stage}"


def stage_from_filename(path: Path) -> str:
    for stage in STAGES:
        if path.name.endswith(f".{stage}"):
            return stage
    raise MigrationError(f"cannot read a stage from env file name {path.name}")


def parse_env_file(path: Path) -> dict[str, str]:
    """Read one env file. Missing file is an error. Keys are not borrowed later."""
    if not path.is_file():
        raise MigrationError(f"missing env file {path}")
    from dotenv import dotenv_values

    raw = dotenv_values(path)
    return {key: value for key, value in raw.items() if key and value is not None}


def connection_settings(env: dict[str, str], prefix: str) -> dict:
    """Every field comes from one prefix. The other prefix is never consulted."""
    if prefix not in PREFIXES:
        raise MigrationError(f"prefix {prefix!r} must be DATABASE or TARGET")
    host = env.get(f"{prefix}_HOST")
    user = env.get(f"{prefix}_USER")
    password = env.get(f"{prefix}_PASSWORD")
    missing = [
        name
        for name, value in (
            (f"{prefix}_HOST", host),
            (f"{prefix}_USER", user),
            (f"{prefix}_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise MigrationError(f"missing {', '.join(missing)}")
    port = int(env.get(f"{prefix}_PORT") or "4000")
    tls_raw = env.get(f"{prefix}_TLS_ENABLED", "true")
    tls = str(tls_raw).lower() in ("1", "true", "yes")
    return {"host": host, "port": port, "user": user, "password": password, "tls": tls}


def resolve_target(
    env: dict[str, str],
    *,
    prefix: str,
    stage: str,
    allow_prod: bool,
    schema: str | None,
) -> tuple[str, dict]:
    """Derive the schema and connection settings. Does not connect."""
    if stage == "prod" and not allow_prod:
        raise MigrationError(f"refusing stage {stage!r}: pass --allow-prod")
    derived = derived_schema(env.get("F3_REGION_NAME", ""), stage)
    if schema is not None and schema != derived:
        raise MigrationError(f"--schema {schema!r} does not match derived schema {derived!r}")
    return derived, connection_settings(env, prefix)


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


def normalize_sql(text: str) -> str:
    """Drop a leading BOM and turn CRLF into LF. Hashing uses the same text."""
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _is_executable_comment(text: str) -> bool:
    return text.startswith("/*!") or text.startswith("/*+") or text.startswith("/*T!")


def _trim_leading(statement: str) -> str:
    """Drop leading whitespace and plain comments. Keep executable comments."""
    s = statement
    while s:
        stripped = s.lstrip(" \t\n")
        if not stripped:
            return ""
        if stripped.startswith("--") and (len(stripped) == 2 or stripped[2] in " \t\n"):
            newline = stripped.find("\n")
            s = "" if newline < 0 else stripped[newline + 1 :]
            continue
        if stripped.startswith("#"):
            newline = stripped.find("\n")
            s = "" if newline < 0 else stripped[newline + 1 :]
            continue
        if stripped.startswith("/*") and not _is_executable_comment(stripped):
            end = stripped.find("*/")
            if end < 0:
                return ""
            s = stripped[end + 2 :]
            continue
        return stripped
    return ""


def split_sql(text: str) -> list[str]:
    """Split on semicolons that end statements. Comments stay in the text.

    Assumes the default sql_mode, so backslash escapes quotes. A line that
    starts with DELIMITER is rejected: migration files have no stored programs.
    """
    text = normalize_sql(text)
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    length = len(text)
    in_single = False
    in_double = False
    in_tick = False
    in_block = False
    in_line = False

    def at_line_start() -> bool:
        return i == 0 or text[i - 1] == "\n"

    while i < length:
        ch = text[i]
        if in_line:
            buf.append(ch)
            if ch == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            buf.append(ch)
            if ch == "*" and i + 1 < length and text[i + 1] == "/":
                buf.append("/")
                i += 2
                in_block = False
                continue
            i += 1
            continue
        if in_single or in_double or in_tick:
            buf.append(ch)
            if ch == "\\" and (in_single or in_double) and i + 1 < length:
                buf.append(text[i + 1])
                i += 2
                continue
            quote = "'" if in_single else ('"' if in_double else "`")
            if ch == quote:
                if i + 1 < length and text[i + 1] == quote:
                    buf.append(quote)
                    i += 2
                    continue
                in_single = in_double = in_tick = False
            i += 1
            continue
        if at_line_start():
            j = i
            while j < length and text[j] in " \t":
                j += 1
            if text.startswith("DELIMITER", j) and (
                j + 9 == length or text[j + 9] in " \t\n"
            ):
                raise MigrationError("DELIMITER is not allowed in migration files")
        if ch == "-" and i + 1 < length and text[i + 1] == "-":
            after = text[i + 2] if i + 2 < length else ""
            if after in ("", " ", "\t", "\n"):
                in_line = True
                buf.append("--")
                i += 2
                continue
        if ch == "#":
            in_line = True
            buf.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < length and text[i + 1] == "*":
            in_block = True
            buf.append("/*")
            i += 2
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == "`":
            in_tick = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            statement = _trim_leading("".join(buf))
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = _trim_leading("".join(buf))
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


def connect(settings: dict):
    import pymysql

    return pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        ssl={"ssl": {}} if settings["tls"] else None,
        autocommit=True,
    )


def load_invocation(args) -> tuple[str, dict]:
    """Resolve schema and connection settings before opening a connection."""
    if args.from_environment and args.env_file:
        raise MigrationError("pass --env-file or --from-environment, not both")
    if args.from_environment:
        stage = args.stage
        if not stage:
            raise MigrationError("--from-environment requires --stage")
        if os.environ.get("STAGE") != stage:
            raise MigrationError(f"STAGE {os.environ.get('STAGE')!r} must equal --stage {stage!r}")
        env = {key: value for key, value in os.environ.items()}
        prefix = "DATABASE"
    else:
        if not args.env_file:
            raise MigrationError("pass --env-file or --from-environment")
        path = Path(args.env_file)
        stage = stage_from_filename(path)
        if args.stage and args.stage != stage:
            raise MigrationError(f"--stage {args.stage!r} does not match {path.name}")
        env = parse_env_file(path)
        prefix = args.prefix
    return resolve_target(
        env,
        prefix=prefix,
        stage=stage,
        allow_prod=args.allow_prod,
        schema=args.schema,
    )


def run(directory: Path, schema: str, settings: dict, *, to: int | None) -> list[int]:
    migrations = discover(directory)
    conn = connect(settings)
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
    parser.add_argument("--env-file", type=Path, help="Env file whose name ends in .<stage>")
    parser.add_argument(
        "--prefix",
        choices=PREFIXES,
        default="DATABASE",
        help="Which variables to read from --env-file. Never mixed.",
    )
    parser.add_argument(
        "--from-environment",
        action="store_true",
        help="Read DATABASE_* and STAGE from the process environment (CI)",
    )
    parser.add_argument("--stage", help="Required with --from-environment. Must equal STAGE.")
    parser.add_argument(
        "--schema",
        help="Optional assertion. Must equal ${F3_REGION_NAME}_<stage>.",
    )
    parser.add_argument(
        "--migrations",
        type=Path,
        default=Path(__file__).resolve().parent / "migrations",
    )
    parser.add_argument("--to", type=int, default=None, help="Apply through this version")
    parser.add_argument(
        "--allow-prod",
        action="store_true",
        help="Required when the stage is prod",
    )
    args = parser.parse_args(argv)
    try:
        schema, settings = load_invocation(args)
        applied = run(args.migrations, schema, settings, to=args.to)
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
