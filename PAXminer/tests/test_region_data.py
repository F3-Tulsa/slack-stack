import os

import pytest

from region_data import database_schema, region_for_team


def test_database_schema_reads_the_one_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_SCHEMA", "f3ttown_test")
    monkeypatch.setenv("PAXMINER_SCHEMA", "paxminer_test")
    assert database_schema() == "f3ttown_test"


def test_database_schema_refuses_a_missing_or_unsafe_name(monkeypatch):
    monkeypatch.delenv("DATABASE_SCHEMA", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_SCHEMA"):
        database_schema()
    monkeypatch.setenv("DATABASE_SCHEMA", "f3ttown-test")
    with pytest.raises(RuntimeError, match="DATABASE_SCHEMA"):
        database_schema()


def test_region_for_team_reads_region_config():
    class Cursor:
        def __init__(self):
            self.sql = ""
            self.params = ()

        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchone(self):
            return {"team_id": self.params[0], "region": "f3ttown"}

    cur = Cursor()
    row = region_for_team(cur, "T1")
    assert "region_config" in cur.sql
    assert "slackblast" not in cur.sql
    assert cur.params == ("T1",)
    assert row["region"] == "f3ttown"


def test_templates_pass_one_schema_name():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    for rel in (
        "PAXminer/template.yaml",
        "slackblast/template.yaml",
        "qsignups/template.yaml",
    ):
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        assert "DATABASE_SCHEMA:" in text
        for gone in (
            "PAXMINER_SCHEMA:",
            "PAXMINER_REGISTRY_DATABASE:",
            "SLACKBLAST_SCHEMA:",
            "PM_REGIONAL_SCHEMA:",
            "ADMIN_DATABASE_SCHEMA:",
        ):
            assert gone not in text, f"{rel} still has {gone}"
