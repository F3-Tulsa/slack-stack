"""Tulsa history: the table setup PAXMiner ran before db/migrations existed.

These copies built Tulsa's PAXMiner, Weaselbot and scheduler tables during the
2026 cutover. A new region gets every table from db/migrations/0001_baseline.sql
and never runs this file. Only the migration/paxminer_phases modules use it,
to replay Tulsa's cutover on a rehearsal copy.

migration/tests/test_legacy_ddl_covered.py checks that 0001 covers every
table, column and view created here. migration/tests/test_no_runtime_ddl.py
checks that no runtime code creates tables.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "PAXminer"))

from scheduling import DEFAULT_TIMEZONE  # noqa: E402

from paxminer_phases.db import _table_exists  # noqa: E402

LOG = logging.getLogger(__name__)


# Achievements (regional schema).

ACHIEVEMENTS_LIST_DDL = """
CREATE TABLE IF NOT EXISTS `{schema}`.`achievements_list` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` varchar(255) NOT NULL,
  `verb` varchar(255) NOT NULL,
  `code` varchar(255) NOT NULL,
  `metric` varchar(32) NOT NULL DEFAULT 'posts',
  `activity` varchar(32) NOT NULL DEFAULT 'beatdown',
  `period` varchar(16) NOT NULL DEFAULT 'year',
  `threshold` int NOT NULL DEFAULT 1,
  `enabled` tinyint NOT NULL DEFAULT 1,
  `reeval_queued_at` datetime DEFAULT NULL,
  `emoji` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

ACHIEVEMENTS_AWARDED_DDL = """
CREATE TABLE IF NOT EXISTS `{schema}`.`achievements_awarded` (
  `id` int NOT NULL AUTO_INCREMENT,
  `achievement_id` int NOT NULL,
  `pax_id` varchar(255) NOT NULL,
  `date_awarded` date NOT NULL,
  `achievement_version_id` int DEFAULT NULL,
  `period` varchar(16) DEFAULT NULL,
  `period_key` varchar(16) DEFAULT NULL,
  `period_start` date DEFAULT NULL,
  `period_end` date DEFAULT NULL,
  `qualifying_count` int DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `achievement_id` (`achievement_id`),
  KEY `pax_id` (`pax_id`),
  UNIQUE KEY `uniq_award_period` (`achievement_id`, `pax_id`, `period_key`),
  CONSTRAINT `achievements_awarded_ibfk_1` FOREIGN KEY (`achievement_id`) REFERENCES `{schema}`.`achievements_list` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

ACHIEVEMENT_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS `{schema}`.`achievement_versions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `achievement_id` int NOT NULL,
  `version` int NOT NULL,
  `version_key` varchar(300) NOT NULL,
  `metric` varchar(32) NOT NULL DEFAULT 'posts',
  `activity` json DEFAULT NULL,
  `period` varchar(16) NOT NULL DEFAULT 'year',
  `threshold` int NOT NULL DEFAULT 1,
  `effective_from` date DEFAULT NULL,
  `effective_to` date DEFAULT NULL,
  `range_mode` varchar(24) DEFAULT NULL,
  `superseded_at` datetime DEFAULT NULL,
  `created_by` varchar(255) DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `version_key` (`version_key`),
  UNIQUE KEY `achievement_version` (`achievement_id`, `version`),
  KEY `achievement_current` (`achievement_id`, `superseded_at`),
  CONSTRAINT `achievement_versions_ibfk_1` FOREIGN KEY (`achievement_id`)
    REFERENCES `{schema}`.`achievements_list` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

ACHIEVEMENTS_VIEW_DDL = """
CREATE OR REPLACE VIEW `{schema}`.`achievements_view` AS
SELECT u.user_name AS pax, u.user_id AS pax_id, al.name, al.description, aa.date_awarded,
       av.version_key
FROM `{schema}`.`users` u
JOIN `{schema}`.`achievements_awarded` aa ON u.user_id = aa.pax_id
JOIN `{schema}`.`achievements_list` al ON aa.achievement_id = al.id
LEFT JOIN `{schema}`.`achievement_versions` av ON aa.achievement_version_id = av.id
"""


# Report scheduler (registry schema).

DDL_REGION_REPORT_DEFINITIONS = """
CREATE TABLE IF NOT EXISTS `{schema}`.`region_report_definitions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schema_name` varchar(45) NOT NULL,
  `code` varchar(64) NOT NULL,
  `name` varchar(120) NOT NULL,
  `report_type` varchar(40) NOT NULL,
  `is_builtin` tinyint NOT NULL DEFAULT 0,
  `is_customized` tinyint NOT NULL DEFAULT 0,
  `enabled` tinyint NOT NULL DEFAULT 1,
  `kind` varchar(20) DEFAULT NULL,
  `source` varchar(40) DEFAULT NULL,
  `fields` json DEFAULT NULL,
  `metric` varchar(40) DEFAULT NULL,
  `aggregation` varchar(40) DEFAULT NULL,
  `group_by` varchar(80) DEFAULT NULL,
  `top_n` int DEFAULT NULL,
  `time_window_type` varchar(20) DEFAULT NULL,
  `window_days` int DEFAULT NULL,
  `window_start` date DEFAULT NULL,
  `window_end` date DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rrd_schema_code` (`schema_name`, `code`),
  KEY `idx_rrd_schema` (`schema_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

DDL_REGION_SCHEDULES = """
CREATE TABLE IF NOT EXISTS `{schema}`.`region_schedules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schema_name` varchar(45) NOT NULL,
  `report_definition_id` int NOT NULL,
  `destination_type` varchar(40) NOT NULL,
  `destination_channels` json DEFAULT NULL,
  `destination_users` json DEFAULT NULL,
  `frequency_type` varchar(20) NOT NULL DEFAULT 'monthly',
  `day_of_week` tinyint DEFAULT NULL,
  `month_day_mode` varchar(20) DEFAULT 'first',
  `day_of_month` tinyint DEFAULT NULL,
  `time_of_day` time NOT NULL DEFAULT '07:00:00',
  `custom_spec` json DEFAULT NULL,
  `enabled` tinyint NOT NULL DEFAULT 1,
  `last_run_on` date DEFAULT NULL,
  `last_run_at` datetime DEFAULT NULL,
  `last_run_status` varchar(20) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rs_schema` (`schema_name`),
  KEY `idx_rs_enabled` (`enabled`),
  CONSTRAINT `fk_rs_definition`
    FOREIGN KEY (`report_definition_id`)
    REFERENCES `{schema}`.`region_report_definitions` (`id`)
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def ensure_timezone_column(cur, pm_schema: str) -> bool:
    """Add regions.timezone if missing. Returns True when a column was added."""
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='region_config' AND COLUMN_NAME='timezone'
        """,
        (pm_schema,),
    )
    if int(cur.fetchone()["c"]) > 0:
        return False
    cur.execute(
        f"""
        ALTER TABLE `{pm_schema}`.`region_config`
        ADD COLUMN `timezone` varchar(45) NOT NULL DEFAULT %s
        """,
        (DEFAULT_TIMEZONE,),
    )
    LOG.info("Added %s.regions.timezone DEFAULT %s", pm_schema, DEFAULT_TIMEZONE)
    return True


def ensure_log_channel_column(cur, pm_schema: str) -> bool:
    """Add nullable regions.log_channel (Slack channel ID) if missing."""
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='region_config' AND COLUMN_NAME='log_channel'
        """,
        (pm_schema,),
    )
    if int(cur.fetchone()["c"]) > 0:
        return False
    cur.execute(
        f"""
        ALTER TABLE `{pm_schema}`.`region_config`
        ADD COLUMN `log_channel` varchar(100) NULL
        """
    )
    LOG.info("Added %s.regions.log_channel", pm_schema)
    return True


def ensure_scheduler_tables(cur, pm_schema: str) -> list[str]:
    """Create scheduler tables if absent. Returns names of tables created this run."""
    created: list[str] = []
    for table, ddl in (
        ("region_report_definitions", DDL_REGION_REPORT_DEFINITIONS),
        ("region_schedules", DDL_REGION_SCHEDULES),
    ):
        existed = _table_exists(cur, pm_schema, table)
        cur.execute(ddl.format(schema=pm_schema))
        if existed:
            LOG.info("Table %s.%s already present (DDL not needed)", pm_schema, table)
        else:
            LOG.info("Created table %s.%s", pm_schema, table)
            created.append(table)
    return created


def ensure_is_customized_column(cur, pm_schema: str) -> bool:
    """Add region_report_definitions.is_customized if missing. Returns True when added."""
    if not _table_exists(cur, pm_schema, "region_report_definitions"):
        return False
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='region_report_definitions'
          AND COLUMN_NAME='is_customized'
        """,
        (pm_schema,),
    )
    if int(cur.fetchone()["c"]) > 0:
        return False
    cur.execute(
        f"""
        ALTER TABLE `{pm_schema}`.`region_report_definitions`
        ADD COLUMN `is_customized` tinyint NOT NULL DEFAULT 0
          AFTER `is_builtin`
        """
    )
    LOG.info("Added %s.region_report_definitions.is_customized", pm_schema)
    return True


def ensure_report_enabled_column(cur, pm_schema: str) -> bool:
    """Add region_report_definitions.enabled if missing. Returns True when added."""
    if not _table_exists(cur, pm_schema, "region_report_definitions"):
        return False
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='region_report_definitions'
          AND COLUMN_NAME='enabled'
        """,
        (pm_schema,),
    )
    if int(cur.fetchone()["c"]) > 0:
        return False
    cur.execute(
        f"""
        ALTER TABLE `{pm_schema}`.`region_report_definitions`
        ADD COLUMN `enabled` tinyint NOT NULL DEFAULT 1
          AFTER `is_customized`
        """
    )
    LOG.info("Added %s.region_report_definitions.enabled", pm_schema)
    return True


def ensure_last_run_at_column(cur, pm_schema: str) -> bool:
    """Add region_schedules.last_run_at if missing. Returns True when added."""
    if not _table_exists(cur, pm_schema, "region_schedules"):
        return False
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='region_schedules'
          AND COLUMN_NAME='last_run_at'
        """,
        (pm_schema,),
    )
    if int(cur.fetchone()["c"]) > 0:
        return False
    cur.execute(
        f"""
        ALTER TABLE `{pm_schema}`.`region_schedules`
        ADD COLUMN `last_run_at` datetime DEFAULT NULL
          AFTER `last_run_on`
        """
    )
    LOG.info("Added %s.region_schedules.last_run_at", pm_schema)
    return True
