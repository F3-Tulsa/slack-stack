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
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.users (
                  user_id varchar(45) NOT NULL PRIMARY KEY,
                  user_name varchar(45) NOT NULL,
                  real_name varchar(45) NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.users (user_id, user_name, real_name) VALUES ('U1', 'Name', 'Real')"
            )
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.aos (
                  channel_id varchar(45) NOT NULL PRIMARY KEY,
                  ao varchar(45) NOT NULL,
                  channel_created int NOT NULL,
                  archived tinyint NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.aos (channel_id, ao, channel_created, archived) VALUES ('C_AO', 'The AO', 1, 0)"
            )
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.beatdowns (
                  ao_id varchar(45) NOT NULL,
                  bd_date date NOT NULL,
                  q_user_id varchar(45) NOT NULL,
                  PRIMARY KEY (ao_id, bd_date, q_user_id)
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.beatdowns (ao_id, bd_date, q_user_id) VALUES ('C_AO', '2026-01-01', 'U1')"
            )
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.bd_attendance (
                  user_id varchar(45) NOT NULL,
                  ao_id varchar(45) NOT NULL,
                  date varchar(45) NOT NULL,
                  q_user_id varchar(45) NOT NULL,
                  PRIMARY KEY (user_id, ao_id, date, q_user_id)
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.bd_attendance (user_id, ao_id, date, q_user_id) VALUES ('U1', 'C_AO', '2026-01-01', 'U1')"
            )
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.qsignups_aos (
                  id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  ao_channel_id varchar(255) NOT NULL,
                  ao_display_name varchar(255) NOT NULL,
                  ao_location_subtitle varchar(255) NOT NULL,
                  team_id varchar(100) NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.qsignups_aos (ao_channel_id, ao_display_name, ao_location_subtitle, team_id) "
                "VALUES ('C_AO', 'The AO', 'park', 'T_FIXTURE')"
            )
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.qsignups_weekly (
                  id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  ao_channel_id varchar(32) NOT NULL,
                  event_day_of_week varchar(16) NOT NULL,
                  event_time varchar(16) NOT NULL,
                  event_type varchar(255) NOT NULL,
                  team_id varchar(32) NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.qsignups_weekly "
                "(ao_channel_id, event_day_of_week, event_time, event_type, team_id) "
                "VALUES ('C_AO', 'Monday', '0530', 'bootcamp', 'T_FIXTURE')"
            )
            cursor.execute(
                """
                CREATE TABLE fixture_qsignups.qsignups_master (
                  id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  ao_channel_id varchar(255) NOT NULL,
                  event_date date NOT NULL,
                  event_time varchar(255) NOT NULL,
                  event_day_of_week varchar(255) NOT NULL,
                  event_type varchar(255) NOT NULL,
                  event_recurring tinyint NOT NULL,
                  team_id varchar(100) NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO fixture_qsignups.qsignups_master "
                "(ao_channel_id, event_date, event_time, event_day_of_week, event_type, event_recurring, team_id) "
                "VALUES ('C_AO', '2026-01-05', '0530', 'Monday', 'bootcamp', 1, 'T_FIXTURE')"
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
            assert copied["users"] == 1
            assert copied["aos"] == 1
            assert copied["beatdowns"] == 1
            assert copied["bd_attendance"] == 1
            assert copied["qsignups_aos"] == 1
            assert copied["qsignups_weekly"] == 1
            assert copied["qsignups_master"] == 1
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
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT email_enabled, email_option_show, editing_locked, postie_format,
                       strava_enabled, default_destination, post_achievements_to_ao
                FROM `{schema}`.region_config
                """
            )
            flags = cursor.fetchone()
            assert list(flags.values()) == [0, 0, 0, 1, 1, "ao_channel", 0]
            cursor.execute(f"DELETE FROM `{schema}`.achievements_list WHERE code='the_priest'")
        again = fresh_install(
            _REPO / "db" / "migrations",
            schema,
            SETTINGS,
            region="citest",
            team_id="T_FIXTURE",
            timezone="America/Chicago",
            to=None,
        )
        assert again["achievements"] == 0
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS c FROM `{schema}`.achievements_list")
            assert int(cursor.fetchone()["c"]) == 13
            from convert_to_baseline import compare_recorded

            assert compare_recorded(cursor, schema, SETTINGS) == []
    finally:
        conn.close()


def test_failed_seed_rolls_back_and_the_next_run_finishes():
    conn = _conn()
    schema = "citest_retry"
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{schema}`")
        import achievements.versions as versions

        real = versions.insert_version
        calls = {"n": 0}

        def fail_fifth(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 5:
                raise RuntimeError("stop the fifth achievement")
            return real(*args, **kwargs)

        versions.insert_version = fail_fifth
        try:
            with pytest.raises(RuntimeError, match="fifth"):
                fresh_install(
                    _REPO / "db" / "migrations",
                    schema,
                    SETTINGS,
                    region="citest",
                    team_id="T_FIXTURE",
                    timezone="America/Chicago",
                    to=None,
                )
        finally:
            versions.insert_version = real
        done = fresh_install(
            _REPO / "db" / "migrations",
            schema,
            SETTINGS,
            region="citest",
            team_id="T_FIXTURE",
            timezone="America/Chicago",
            to=None,
        )
        assert done["achievements"] == 14
        assert done["reports"] == {"definitions": 8, "schedules": 8}
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS c FROM `{schema}`.achievement_versions")
            assert int(cursor.fetchone()["c"]) == 14
    finally:
        conn.close()
