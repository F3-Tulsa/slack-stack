"""deploy.sh must not create GitHub environments on the Community repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy.sh"


def _function(name: str) -> str:
    text = _DEPLOY.read_text(encoding="utf-8")
    start = text.index(f"{name}() {{")
    end = text.index("\n}\n", start)
    return text[start : end + 3]


def test_community_repo_is_refused_and_a_region_fork_is_not():
    function = _function("refuse_community_repo")
    refused = subprocess.run(
        ["bash", "-c", function + '\nrefuse_community_repo "F3Nation-Community/slack-stack"\n'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode == 1
    assert "refusing to create a GitHub environment" in refused.stderr
    allowed = subprocess.run(
        ["bash", "-c", function + '\nrefuse_community_repo "example-region/slack-stack"\n'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert allowed.returncode == 0


def test_setup_github_sets_the_flags_a_new_region_needs():
    text = _DEPLOY.read_text(encoding="utf-8")
    setup = text.split("run_setup_github() {", 1)[1].split("\n}\n", 1)[0]
    assert "refuse_community_repo" in setup
    assert "ENABLE_XRAY" in setup
    assert "RUN_EXTEND_SCHEDULE" in setup
    assert "CREATE_OAUTH_TABLES" not in setup
    assert "PAXMINER_SCHEMA" not in setup
    assert "QSIGNUPS_SCHEMA" not in setup
    assert "SLACKBLAST_SCHEMA" not in setup
