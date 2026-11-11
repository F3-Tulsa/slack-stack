"""App code creates no tables, columns or views; db/migrations does.

Covers the copies retire-copies removed: PAXMiner's CREATE TABLE and ensure_*
ALTERs, the seeder's DDL, slackblast's local-database script, and Bolt's
create_tables() behind CREATE_OAUTH_TABLES. Tulsa's cutover DDL lives under
migration/, and qsignups/db is the old-system fixture for the importer test;
neither is scanned.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

RUNTIME_ROOTS = (
    _REPO / "PAXminer",
    _REPO / "slackblast" / "slackblast",
    _REPO / "qsignups" / "qsignups",
    _REPO / "common",
)
SKIP_PARTS = {"tests", "test", "testing", "__pycache__", "site-packages"}

DDL = re.compile(
    r"\bCREATE\s+(?:TEMPORARY\s+)?TABLE\b"
    r"|\bALTER\s+TABLE\b"
    r"|\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:ALGORITHM\s*=\s*\w+\s+)?(?:SQL\s+SECURITY\s+\w+\s+)?VIEW\b"
    r"|\.create_tables\(|\bcreate_all\(",
    re.IGNORECASE,
)

DEPLOY_FILES = (
    _REPO / "deploy.sh",
    _REPO / ".github" / "workflows" / "deploy.yml",
    _REPO / "slackblast" / "template.yaml",
    _REPO / "qsignups" / "template.yaml",
    _REPO / ".env.deploy.example",
)


def _runtime_files():
    for root in RUNTIME_ROOTS:
        for path in sorted(root.rglob("*")):
            if path.suffix not in (".py", ".sql") or not path.is_file():
                continue
            parts = path.relative_to(_REPO).parts
            if any(part in SKIP_PARTS or part.startswith(".") for part in parts):
                continue
            yield path


def test_runtime_code_has_no_ddl():
    hits = []
    for path in _runtime_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if DDL.search(line):
                hits.append(f"{path.relative_to(_REPO)}:{number}: {line.strip()}")
    assert not hits, "runtime DDL found; add a numbered file under db/migrations instead:\n" + "\n".join(hits)


def test_scan_reaches_the_runtime_packages():
    names = {path.relative_to(_REPO).as_posix() for path in _runtime_files()}
    for expected in (
        "PAXminer/slack_app.py",
        "PAXminer/scripts/seed_test_region.py",
        "slackblast/slackblast/utilities/helper_functions.py",
        "qsignups/qsignups/app.py",
    ):
        assert expected in names


def test_oauth_table_switch_is_gone_from_deploy():
    for path in DEPLOY_FILES:
        text = path.read_text(encoding="utf-8")
        assert "CREATE_OAUTH_TABLES" not in text, path
        assert "CreateOauthTables" not in text, path


def test_local_database_script_is_gone():
    database = _REPO / "slackblast" / "slackblast" / "utilities" / "database"
    assert not (database / "create_clear_local_db.py").exists()
    assert not (database / "create_clear_local_db.sql").exists()
