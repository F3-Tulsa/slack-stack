"""Empty MySQL proof for fresh install and the legacy import order.

CI sets REQUIRE_MYSQL=1 and a mysql:8.4 service. Locally the test skips
when that variable is unset.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "db"))
sys.path.insert(0, str(_REPO / "migration"))

from fresh_install import fresh_install  # noqa: E402
from legacy_import import import_rows  # noqa: E402
from migrate import MigrationError, connect, run  # noqa: E402

SETTINGS = {
    "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", "fresh"),
    "tls": False,
}


def _conn():
    if os.environ.get("REQUIRE_MYSQL") != "1":
        pytest.skip("REQUIRE_MYSQL is not set")
    return connect(SETTINGS)


def test_migrate_then_import_then_fresh_install_is_idempotent():
    conn = _conn()
    schema = "citest_test"
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{schema}`")
            cursor.execute("DROP DATABASE IF EXISTS fixture_qsignups")
            cursor.execute("CREATE DATABASE fixture_qsignups")
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.qsignups_regions (
                  id int NOT NULL AUTO_INCREMENT,
                  team_id varchar(100) NOT NULL,
                  bot_token varchar(100) DEFAULT NULL,
                  google_auth_data longtext,
                  timezone varchar(45) DEFAULT NULL,
                  PRIMARY KEY (id),
                  UNIQUE KEY region_idx (team_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.qsignups_features (
                  id int NOT NULL AUTO_INCREMENT,
                  region_id int NOT NULL,
                  feature varchar(45) NOT NULL,
                  enabled tinyint NOT NULL,
                  PRIMARY KEY (id)
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.qsignups_regions (team_id, google_auth_data, timezone) "
                "VALUES ('T_FIXTURE', '{\"secret\":true}', 'America/Chicago')"
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.qsignups_features (region_id, feature, enabled) VALUES (1, 'ours', 1)"
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.qsignups_features (region_id, feature, enabled) VALUES (99, 'theirs', 1)"
            )
        run(_REPO / "db" / "migrations", schema, SETTINGS, to=1, check=False)
        with conn.cursor() as cursor:
            copied = import_rows(
                cursor,
                source_schema="fixture_qsignups",
                qsignups_schema="fixture_qsignups",
                target_schema=schema,
                team_id="T_FIXTURE",
            )
            assert copied["qsignups_regions"] == 1
            assert copied["qsignups_features"] == 1
            cursor.execute(f"SELECT google_auth_data FROM `{schema}`.qsignups_regions")
            assert cursor.fetchone()["google_auth_data"] is None
            with pytest.raises(MigrationError, match="already has rows"):
                import_rows(
                    cursor,
                    source_schema="fixture_qsignups",
                    qsignups_schema="fixture_qsignups",
                    target_schema=schema,
                    team_id="T_FIXTURE",
                )
        first = fresh_install(
            _REPO / "db" / "migrations",
            schema,
            SETTINGS,
            region="citest",
            team_id="T_FIXTURE",
            timezone="America/Chicago",
            to=None,
        )
        assert first["qsignups_regions"] == "kept"
        assert first["achievements"] == 14
        second = fresh_install(
            _REPO / "db" / "migrations",
            schema,
            SETTINGS,
            region="citest",
            team_id="T_FIXTURE",
            timezone="America/Chicago",
            to=None,
        )
        assert second["achievements"] == 0
        assert second["reports"] == {"definitions": 0, "schedules": 0}
    finally:
        conn.close()
