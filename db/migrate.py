"""Forward-only numbered SQL runner.

Files live in ``db/migrations/NNNN_slug.sql``. The runner creates
``schema_migrations`` itself and records a file only after every statement
in it has been sent. MySQL and TiDB commit each DDL statement immediately,
so a failure midway leaves the earlier statements applied. The file is not
recorded, and the error says which statements already ran.

``deploy.sh`` and ``deploy.yml`` do not call this module.
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
CREATE_INDEX = re.compile(
    r"^CREATE\s+(?:UNIQUE\s+|FULLTEXT\s+|SPATIAL\s+)?INDEX\b",
    re.IGNORECASE,
)
CREATE_CLAUSE = re.compile(
    r"^(?:ALGORITHM\s*=\s*\w+|DEFINER\s*=\s*\S+|SQL\s+SECURITY\s+\w+)\s+",
    re.IGNORECASE,
)
CREATE_OBJECT = re.compile(
    r"^(TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:[`'\"]?[A-Za-z0-9_]+[`'\"]?\s*\.\s*)?"
    r"[`'\"]?([A-Za-z0-9_]+)",
    re.IGNORECASE,
)
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
        if version == 0:
            raise MigrationError("migration numbers start at 0001")
        if version in found:
            raise MigrationError(f"duplicate migration number {version:04d}")
        sql = normalize_sql(path.read_text(encoding="utf-8-sig"))
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
            word = text[j : j + 9]
            if word.lower() == "delimiter" and (
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
    if in_block or in_single or in_double or in_tick:
        kind = "comment" if in_block else ("string" if in_single or in_double else "identifier")
        raise MigrationError(f"SQL ends inside an unclosed {kind}")
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


@dataclass(frozen=True)
class History:
    pending: list[int]
    ahead: list[int]


@dataclass(frozen=True)
class ApplyResult:
    applied: list[int]
    ahead: list[int]


def plan_history(migrations: list[Migration], recorded: dict[int, str] | None) -> History:
    """Compare files with what the schema has recorded.

    A missing bookkeeping table (``recorded is None``) means every file is
    pending. A recorded checksum that does not match the file is an error.
    A recorded version with no file means the schema is ahead of this code.
    """
    if recorded is None:
        return History([migration.version for migration in migrations], [])
    by_version = {migration.version: migration for migration in migrations}
    ahead: list[int] = []
    for version, checksum in sorted(recorded.items()):
        migration = by_version.get(version)
        if migration is None:
            ahead.append(version)
            continue
        if migration.checksum != checksum:
            raise MigrationError(
                f"{version:04d}_{migration.name} checksum changed "
                f"after it was applied ({checksum} != {migration.checksum})"
            )
    pending = [
        migration.version
        for migration in migrations
        if migration.version not in recorded
    ]
    return History(pending, ahead)


def apply_pending(cursor, migrations: list[Migration], *, to: int | None = None) -> ApplyResult:
    """Apply files whose version is not recorded. Validate every recorded row first."""
    recorded = _applied(cursor)
    history = plan_history(migrations, recorded)
    done: list[int] = []
    for migration in migrations:
        if migration.version not in history.pending:
            continue
        if to is not None and migration.version > to:
            continue
        statements = split_sql(migration.sql)
        for index, statement in enumerate(statements, start=1):
            try:
                cursor.execute(statement)
            except Exception as exc:
                earlier = index - 1
                detail = f"{migration.version:04d}_{migration.name} failed on: {statement}"
                if earlier:
                    detail += (
                        f"; statements 1-{earlier} of {len(statements)} already ran "
                        "and were not rolled back; repair the schema by hand"
                    )
                raise MigrationError(detail) from exc
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
    return ApplyResult(done, history.ahead)


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
        if args.prefix != "DATABASE":
            raise MigrationError("--from-environment reads DATABASE_* only")
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


def _missing_relation(exc: Exception) -> bool:
    text = str(exc).lower()
    return "doesn't exist" in text or "does not exist" in text or "unknown database" in text


def recorded_or_none(cursor) -> dict[int, str] | None:
    try:
        return _applied(cursor)
    except Exception as exc:
        if _missing_relation(exc):
            return None
        raise


def _name_finding_text(statement: str) -> str:
    """Drop mysqldump version-comment markers. The executed statement is unchanged."""
    return re.sub(r"/\*!\d+\s*", "", statement).replace("*/", "")


def object_name(statement: str) -> str | None:
    """Return the table or view a CREATE statement names.

    ``None`` means the statement is not a CREATE, or it is a CREATE INDEX.
    Any other CREATE that yields no name is an error.
    """
    text = _name_finding_text(statement).strip()
    if not re.match(r"CREATE\b", text, re.IGNORECASE):
        return None
    if CREATE_INDEX.match(text):
        return None
    rest = re.sub(r"^CREATE\s+(?:OR\s+REPLACE\s+)?", "", text, count=1, flags=re.IGNORECASE)
    while True:
        clause = CREATE_CLAUSE.match(rest)
        if clause is None:
            break
        rest = rest[clause.end() :]
    match = CREATE_OBJECT.match(rest)
    if match is None:
        raise MigrationError("cannot name CREATE: " + " ".join(text.split())[:80])
    return match.group(2)


def created_names(migrations: list[Migration]) -> list[str]:
    """Table and view names from CREATE statements. This is not a SQL parser."""
    names: list[str] = []
    for migration in migrations:
        for statement in split_sql(migration.sql):
            name = object_name(statement)
            if name:
                names.append(name)
    return names


def mark_applied(
    cursor,
    schema: str,
    migrations: list[Migration],
    version: int,
    *,
    yes: bool,
) -> list[int]:
    """Record versions 1..N without executing them. Dry run unless yes."""
    if not migrations:
        raise MigrationError("no migration files to mark")
    highest = migrations[-1].version
    if version < 1 or version > highest:
        raise MigrationError(f"--mark-applied {version} is past the last file {highest:04d}")
    chosen = [migration for migration in migrations if migration.version <= version]
    names = created_names(chosen)
    if not names:
        raise MigrationError("these files create nothing, so there is nothing to check")
    recorded = recorded_or_none(cursor)
    if recorded:
        raise MigrationError("schema_migrations already has rows")
    missing = []
    for name in names:
        cursor.execute(
            """
            SELECT TABLE_NAME AS name FROM information_schema.TABLES
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            """,
            (schema, name),
        )
        if cursor.fetchone() is None:
            missing.append(name)
    if missing:
        raise MigrationError("missing tables or views: " + ", ".join(missing))
    if not yes:
        return [migration.version for migration in chosen]
    ensure_bookkeeping(cursor)
    for migration in chosen:
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
    return [migration.version for migration in chosen]


def run(directory: Path, schema: str, settings: dict, *, to: int | None, check: bool) -> History | ApplyResult:
    migrations = discover(directory)
    conn = connect(settings)
    try:
        with conn.cursor() as cursor:
            if check:
                try:
                    cursor.execute(f"USE `{schema}`")
                except Exception as exc:
                    if _missing_relation(exc):
                        return plan_history(migrations, None)
                    raise
                return plan_history(migrations, recorded_or_none(cursor))
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{schema}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
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
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report pending and ahead versions without writing",
    )
    parser.add_argument(
        "--mark-applied",
        type=int,
        default=None,
        metavar="N",
        help="Record files 1..N without executing them",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Write the rows for --mark-applied. Without this, it only prints.",
    )
    args = parser.parse_args(argv)
    try:
        schema, settings = load_invocation(args)
        if args.mark_applied is not None:
            migrations = discover(args.migrations)
            conn = connect(settings)
            try:
                with conn.cursor() as cursor:
                    try:
                        cursor.execute(f"USE `{schema}`")
                    except Exception as exc:
                        if _missing_relation(exc):
                            raise MigrationError(
                                f"schema {schema} does not exist; "
                                "--mark-applied adopts an existing schema"
                            ) from exc
                        raise
                    marked = mark_applied(
                        cursor,
                        schema,
                        migrations,
                        args.mark_applied,
                        yes=args.yes,
                    )
            finally:
                conn.close()
            verb = "recorded" if args.yes else "would record"
            print(verb + " " + ", ".join(f"{n:04d}" for n in marked))
            return 0
        result = run(args.migrations, schema, settings, to=args.to, check=args.check)
    except Exception as exc:
        import pymysql

        if not isinstance(exc, (MigrationError, pymysql.err.MySQLError)):
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if isinstance(result, History):
        if result.ahead:
            print(
                "schema is ahead of this code: "
                + ", ".join(f"{n:04d}" for n in result.ahead),
                file=sys.stderr,
            )
        if result.pending:
            print("pending " + ", ".join(f"{n:04d}" for n in result.pending))
            return 1
        print("schema is current")
        return 0
    if result.ahead:
        print(
            "warning: schema is ahead of this code: "
            + ", ".join(f"{n:04d}" for n in result.ahead),
            file=sys.stderr,
        )
    if result.applied:
        print("applied " + ", ".join(f"{n:04d}" for n in result.applied))
    else:
        print("no pending migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
