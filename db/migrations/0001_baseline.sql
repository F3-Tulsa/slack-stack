-- Baseline schema for one region, generated from the rehearsed consolidated schema on 2026-11-06.
-- The runner selects the schema. This file names no database.
-- Tables use IF NOT EXISTS so a retry after a mid-file failure can continue.

CREATE TABLE IF NOT EXISTS `achievement_versions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `achievement_id` int NOT NULL,
  `version` int NOT NULL,
  `version_key` varchar(300) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'posts',
  `activity` json DEFAULT NULL,
  `period` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'year',
  `threshold` int NOT NULL DEFAULT '1',
  `effective_from` date DEFAULT NULL,
  `effective_to` date DEFAULT NULL,
  `range_mode` varchar(24) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `superseded_at` datetime DEFAULT NULL,
  `created_by` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `version_key` (`version_key`),
  UNIQUE KEY `achievement_version` (`achievement_id`,`version`),
  KEY `achievement_current` (`achievement_id`,`superseded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `achievements_awarded` (
  `id` int NOT NULL AUTO_INCREMENT,
  `achievement_id` int NOT NULL,
  `pax_id` varchar(255) NOT NULL,
  `date_awarded` date NOT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `achievement_version_id` int DEFAULT NULL,
  `period` varchar(16) DEFAULT NULL,
  `period_key` varchar(16) DEFAULT NULL,
  `period_start` date DEFAULT NULL,
  `period_end` date DEFAULT NULL,
  `qualifying_count` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_achievement_id` (`achievement_id`),
  UNIQUE KEY `uniq_award_period` (`achievement_id`,`pax_id`,`period_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `achievements_list` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `verb` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(255) NOT NULL,
  `metric` varchar(32) NOT NULL DEFAULT 'posts',
  `activity` varchar(32) NOT NULL DEFAULT 'beatdown',
  `period` varchar(32) NOT NULL DEFAULT 'year',
  `threshold` int NOT NULL DEFAULT '1',
  `enabled` tinyint NOT NULL DEFAULT '1',
  `reeval_queued_at` datetime DEFAULT NULL,
  `emoji` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `aos` (
  `channel_id` varchar(45) NOT NULL,
  `ao` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  `channel_created` int NOT NULL,
  `archived` tinyint NOT NULL,
  `backblast` tinyint DEFAULT NULL,
  `site_q_user_id` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`channel_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `bd_attendance` (
  `timestamp` varchar(45) DEFAULT NULL,
  `ts_edited` varchar(45) DEFAULT NULL,
  `user_id` varchar(45) NOT NULL,
  `ao_id` varchar(45) NOT NULL,
  `date` varchar(45) NOT NULL,
  `q_user_id` varchar(45) NOT NULL,
  `json` json DEFAULT NULL,
  PRIMARY KEY (`user_id`,`ao_id`,`date`,`q_user_id`),
  KEY `fk_bd_attendance_aos1_idx` (`ao_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `beatdowns` (
  `timestamp` varchar(45) DEFAULT NULL,
  `ts_edited` varchar(45) DEFAULT NULL,
  `ao_id` varchar(45) NOT NULL,
  `bd_date` date NOT NULL,
  `q_user_id` varchar(45) NOT NULL,
  `coq_user_id` varchar(45) DEFAULT NULL,
  `pax_count` int DEFAULT NULL,
  `backblast` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `backblast_parsed` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fngs` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fng_count` int DEFAULT NULL,
  `json` json DEFAULT NULL,
  `activity_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`ao_id`,`bd_date`,`q_user_id`),
  KEY `fk_beatdowns_users1_idx` (`q_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `interaction_claims` (
  `claim_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `kind` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `team_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`claim_key`,`kind`),
  KEY `idx_interaction_claims_team` (`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Claim view.id before Slack post so retries cannot duplicate messages';

CREATE TABLE IF NOT EXISTS `qsignups_aos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ao_channel_id` varchar(255) NOT NULL,
  `ao_display_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ao_location_subtitle` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `team_id` varchar(100) NOT NULL,
  `current_month_weinke` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `aos_idx` (`ao_channel_id`,`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `qsignups_features` (
  `id` int NOT NULL AUTO_INCREMENT,
  `region_id` int NOT NULL,
  `feature` varchar(45) NOT NULL,
  `enabled` tinyint NOT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `region_id_fk` (`region_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `qsignups_master` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ao_channel_id` varchar(255) NOT NULL,
  `event_date` date NOT NULL,
  `event_time` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_end_time` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_day_of_week` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_special` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_recurring` tinyint(1) NOT NULL,
  `q_pax_id` varchar(255) DEFAULT NULL,
  `q_pax_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `team_id` varchar(100) NOT NULL,
  `google_event_id` varchar(45) DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `master_idx` (`ao_channel_id`,`event_date`,`event_time`,`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `qsignups_regions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `current_week_weinke` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `next_week_weinke` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `team_id` varchar(100) NOT NULL,
  `bot_token` varchar(512) DEFAULT NULL,
  `signup_reminders` tinyint DEFAULT NULL,
  `weekly_weinke_channel` varchar(100) DEFAULT NULL,
  `workspace_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `current_week_weinke_updated` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `next_week_weinke_updated` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `weekly_ao_reminders` tinyint(1) DEFAULT NULL,
  `google_calendar_id` varchar(100) DEFAULT NULL,
  `google_auth_data` longtext DEFAULT NULL,
  `timezone` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `region_idx` (`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `qsignups_weekly` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ao_channel_id` varchar(32) NOT NULL,
  `event_day_of_week` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_time` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_end_time` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_type` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `team_id` varchar(32) NOT NULL,
  `google_calendar_id` varchar(100) DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `weekly_idx` (`ao_channel_id`,`event_day_of_week`,`event_time`,`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `region_config` (
  `region` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  `schema_name` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `active` tinyint DEFAULT NULL,
  `slack_token` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contact` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `scrape_backblasts` tinyint DEFAULT NULL,
  `comments` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `send_achievements` tinyint DEFAULT NULL,
  `region_achievements_channel` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `NO_POST_THRESHOLD` int DEFAULT NULL,
  `REMINDER_WEEKS` int DEFAULT NULL,
  `HOME_AO_CAPTURE` int DEFAULT NULL,
  `NO_Q_THRESHOLD_WEEKS` int DEFAULT NULL,
  `NO_Q_THRESHOLD_POSTS` int DEFAULT NULL,
  `timezone` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'America/Chicago',
  `log_channel` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `team_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `workspace_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sb_bot_token` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email_enabled` tinyint DEFAULT NULL,
  `email_server` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email_server_port` int DEFAULT NULL,
  `email_user` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email_password` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email_to` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email_option_show` tinyint DEFAULT NULL,
  `postie_format` tinyint DEFAULT NULL,
  `editing_locked` tinyint DEFAULT NULL,
  `default_destination` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `backblast_moleskin_template` json DEFAULT NULL,
  `preblast_moleskin_template` json DEFAULT NULL,
  `strava_enabled` tinyint DEFAULT NULL,
  `custom_fields` json DEFAULT NULL,
  `welcome_dm_enable` tinyint DEFAULT NULL,
  `welcome_dm_template` json DEFAULT NULL,
  `welcome_channel_enable` tinyint DEFAULT NULL,
  `welcome_channel` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `post_achievements_to_ao` tinyint DEFAULT NULL,
  `created` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`region`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `region_report_definitions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schema_name` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `report_type` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_builtin` tinyint NOT NULL DEFAULT '0',
  `is_customized` tinyint NOT NULL DEFAULT '0',
  `enabled` tinyint NOT NULL DEFAULT '1',
  `kind` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fields` json DEFAULT NULL,
  `metric` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `aggregation` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `group_by` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `top_n` int DEFAULT NULL,
  `time_window_type` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `window_days` int DEFAULT NULL,
  `window_start` date DEFAULT NULL,
  `window_end` date DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rrd_schema_code` (`schema_name`,`code`),
  KEY `idx_rrd_schema` (`schema_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `region_schedules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schema_name` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  `report_definition_id` int NOT NULL,
  `destination_type` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `destination_channels` json DEFAULT NULL,
  `destination_users` json DEFAULT NULL,
  `frequency_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'monthly',
  `day_of_week` tinyint DEFAULT NULL,
  `month_day_mode` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'first',
  `day_of_month` tinyint DEFAULT NULL,
  `time_of_day` time NOT NULL DEFAULT '07:00:00',
  `custom_spec` json DEFAULT NULL,
  `enabled` tinyint NOT NULL DEFAULT '1',
  `last_run_on` date DEFAULT NULL,
  `last_run_at` datetime DEFAULT NULL,
  `last_run_status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rs_schema` (`schema_name`),
  KEY `idx_rs_enabled` (`enabled`),
  KEY `fk_rs_definition` (`report_definition_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `slack_bots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `client_id` varchar(32) NOT NULL,
  `app_id` varchar(32) NOT NULL,
  `enterprise_id` varchar(32) DEFAULT NULL,
  `enterprise_name` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `team_id` varchar(32) DEFAULT NULL,
  `team_name` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bot_token` varchar(200) DEFAULT NULL,
  `bot_id` varchar(32) DEFAULT NULL,
  `bot_user_id` varchar(32) DEFAULT NULL,
  `bot_scopes` varchar(1000) DEFAULT NULL,
  `bot_refresh_token` varchar(200) DEFAULT NULL,
  `bot_token_expires_at` datetime DEFAULT NULL,
  `is_enterprise_install` tinyint(1) NOT NULL,
  `installed_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `slack_bots_idx` (`client_id`,`enterprise_id`,`team_id`,`installed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `slack_installations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `client_id` varchar(32) NOT NULL,
  `app_id` varchar(32) NOT NULL,
  `enterprise_id` varchar(32) DEFAULT NULL,
  `enterprise_name` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `enterprise_url` varchar(200) DEFAULT NULL,
  `team_id` varchar(32) DEFAULT NULL,
  `team_name` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bot_token` varchar(200) DEFAULT NULL,
  `bot_id` varchar(32) DEFAULT NULL,
  `bot_user_id` varchar(32) DEFAULT NULL,
  `bot_scopes` varchar(1000) DEFAULT NULL,
  `bot_refresh_token` varchar(200) DEFAULT NULL,
  `bot_token_expires_at` datetime DEFAULT NULL,
  `user_id` varchar(32) NOT NULL,
  `user_token` varchar(200) DEFAULT NULL,
  `user_scopes` varchar(1000) DEFAULT NULL,
  `user_refresh_token` varchar(200) DEFAULT NULL,
  `user_token_expires_at` datetime DEFAULT NULL,
  `incoming_webhook_url` varchar(200) DEFAULT NULL,
  `incoming_webhook_channel` varchar(200) DEFAULT NULL,
  `incoming_webhook_channel_id` varchar(200) DEFAULT NULL,
  `incoming_webhook_configuration_url` varchar(200) DEFAULT NULL,
  `is_enterprise_install` tinyint(1) NOT NULL,
  `token_type` varchar(32) DEFAULT NULL,
  `installed_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `slack_installations_idx` (`client_id`,`enterprise_id`,`team_id`,`user_id`,`installed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `slack_oauth_states` (
  `id` int NOT NULL AUTO_INCREMENT,
  `state` varchar(200) NOT NULL,
  `expire_at` datetime NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `slackblast_users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `team_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `strava_access_token` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `strava_refresh_token` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `strava_expires_at` datetime DEFAULT NULL,
  `strava_athlete_id` int DEFAULT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users` (
  `user_id` varchar(45) NOT NULL,
  `user_name` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  `real_name` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  `phone` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `start_date` date DEFAULT NULL,
  `app` tinyint NOT NULL DEFAULT '0',
  `json` json DEFAULT NULL,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `welcome_deliveries` (
  `event_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `destination` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `team_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`event_id`,`destination`),
  KEY `idx_welcome_deliveries_team_user` (`team_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW `achievements_view` (`pax`, `pax_id`, `name`, `description`, `date_awarded`, `version_key`) AS SELECT `u`.`user_name` AS `pax`,`u`.`user_id` AS `pax_id`,`al`.`name` AS `name`,`al`.`description` AS `description`,`aa`.`date_awarded` AS `date_awarded`,`av`.`version_key` AS `version_key` FROM ((`users` AS `u` JOIN `achievements_awarded` AS `aa` ON `u`.`user_id`=`aa`.`pax_id`) JOIN `achievements_list` AS `al` ON `aa`.`achievement_id`=`al`.`id`) LEFT JOIN `achievement_versions` AS `av` ON `aa`.`achievement_version_id`=`av`.`id`;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW `attendance_view` (`Date`, `AO`, `PAX`, `Q`) AS SELECT `bd`.`date` AS `Date`,`ao`.`ao` AS `AO`,`u`.`user_name` AS `PAX`,`q`.`user_name` AS `Q` FROM ((`bd_attendance` AS `bd` LEFT JOIN `aos` AS `ao` ON ((`bd`.`ao_id`=`ao`.`channel_id`))) LEFT JOIN `users` AS `u` ON ((`bd`.`user_id`=`u`.`user_id`))) LEFT JOIN `users` AS `q` ON ((`bd`.`q_user_id`=`q`.`user_id`)) ORDER BY `bd`.`date` DESC,`ao`.`ao`;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW `backblast` (`Date`, `AO`, `Q`, `CoQ`, `pax_count`, `pax_names`, `fngs`, `fng_count`, `backblast`) AS SELECT `B`.`bd_date` AS `Date`,`A`.`ao` AS `AO`,`U1`.`user_name` AS `Q`,`U2`.`user_name` AS `CoQ`,`B`.`pax_count` AS `pax_count`,`P`.`pax_names` AS `pax_names`,`B`.`fngs` AS `fngs`,`B`.`fng_count` AS `fng_count`,COALESCE(`B`.`backblast_parsed`, `B`.`backblast`) AS `backblast` FROM (((`beatdowns` AS `B` JOIN `users` AS `U1` ON `U1`.`user_id`=`B`.`q_user_id`) LEFT JOIN `aos` AS `A` ON `A`.`channel_id`=`B`.`ao_id`) LEFT JOIN `users` AS `U2` ON `U2`.`user_id`=`B`.`coq_user_id`) LEFT JOIN (SELECT `bd`.`ao_id` AS `ao_id`,`bd`.`date` AS `bd_date`,`bd`.`q_user_id` AS `q_user_id`,GROUP_CONCAT(`u`.`user_name` ORDER BY `u`.`user_name` SEPARATOR ', ') AS `pax_names` FROM `bd_attendance` AS `bd` LEFT JOIN `users` AS `u` ON `u`.`user_id`=`bd`.`user_id` GROUP BY `bd`.`ao_id`,`bd`.`date`,`bd`.`q_user_id`) AS `P` ON `P`.`ao_id`=`B`.`ao_id` AND `P`.`bd_date`=`B`.`bd_date` AND `P`.`q_user_id`=`B`.`q_user_id` ORDER BY `B`.`bd_date`,`A`.`ao`;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW `beatdown_info` (`Date`, `AO`, `Q`, `Q_Is_App`, `CoQ`, `pax_count`, `fngs`, `fng_count`) AS SELECT `B`.`bd_date` AS `Date`,`a`.`ao` AS `AO`,`U1`.`user_name` AS `Q`,`U1`.`app` AS `Q_Is_App`,`U2`.`user_name` AS `CoQ`,`B`.`pax_count` AS `pax_count`,`B`.`fngs` AS `fngs`,`B`.`fng_count` AS `fng_count` FROM ((`beatdowns` AS `B` LEFT JOIN `users` AS `U1` ON ((`U1`.`user_id`=`B`.`q_user_id`))) LEFT JOIN `users` AS `U2` ON ((`U2`.`user_id`=`B`.`coq_user_id`))) LEFT JOIN `aos` AS `a` ON ((`a`.`channel_id`=`B`.`ao_id`)) ORDER BY `B`.`bd_date`,`a`.`ao`;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW `vw_aos_sort` (`id`, `ao_channel_id`, `ao_display_name`, `ao_location_subtitle`, `team_id`, `current_month_weinke`, `created`, `updated`) AS SELECT `qsignups_aos`.`id` AS `id`,`qsignups_aos`.`ao_channel_id` AS `ao_channel_id`,`qsignups_aos`.`ao_display_name` AS `ao_display_name`,`qsignups_aos`.`ao_location_subtitle` AS `ao_location_subtitle`,`qsignups_aos`.`team_id` AS `team_id`,`qsignups_aos`.`current_month_weinke` AS `current_month_weinke`,`qsignups_aos`.`created` AS `created`,`qsignups_aos`.`updated` AS `updated` FROM `qsignups_aos` ORDER BY REPLACE(`ao_display_name`, _UTF8MB4'The ', _UTF8MB4'');

CREATE OR REPLACE SQL SECURITY INVOKER VIEW `vw_master_events` (`id`, `ao_channel_id`, `event_date`, `event_time`, `event_end_time`, `event_day_of_week`, `event_type`, `event_special`, `event_recurring`, `q_pax_id`, `q_pax_name`, `team_id`, `google_event_id`, `created`, `updated`, `ao_display_name`, `ao_location_subtitle`) AS SELECT `m`.`id` AS `id`,`m`.`ao_channel_id` AS `ao_channel_id`,`m`.`event_date` AS `event_date`,`m`.`event_time` AS `event_time`,`m`.`event_end_time` AS `event_end_time`,`m`.`event_day_of_week` AS `event_day_of_week`,`m`.`event_type` AS `event_type`,`m`.`event_special` AS `event_special`,`m`.`event_recurring` AS `event_recurring`,`m`.`q_pax_id` AS `q_pax_id`,`m`.`q_pax_name` AS `q_pax_name`,`m`.`team_id` AS `team_id`,`m`.`google_event_id` AS `google_event_id`,`m`.`created` AS `created`,`m`.`updated` AS `updated`,`a`.`ao_display_name` AS `ao_display_name`,`a`.`ao_location_subtitle` AS `ao_location_subtitle` FROM `qsignups_master` AS `m` LEFT JOIN `qsignups_aos` AS `a` ON `m`.`team_id`=`a`.`team_id` AND `m`.`ao_channel_id`=`a`.`ao_channel_id` ORDER BY `m`.`event_date`,`m`.`event_time`;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW `vw_weekly_events` (`id`, `ao_channel_id`, `event_day_of_week`, `event_time`, `event_end_time`, `event_type`, `team_id`, `google_calendar_id`, `created`, `updated`, `ao_display_name`) AS SELECT `w`.`id` AS `id`,`w`.`ao_channel_id` AS `ao_channel_id`,`w`.`event_day_of_week` AS `event_day_of_week`,`w`.`event_time` AS `event_time`,`w`.`event_end_time` AS `event_end_time`,`w`.`event_type` AS `event_type`,`w`.`team_id` AS `team_id`,`w`.`google_calendar_id` AS `google_calendar_id`,`w`.`created` AS `created`,`w`.`updated` AS `updated`,`a`.`ao_display_name` AS `ao_display_name` FROM `qsignups_weekly` AS `w` JOIN `qsignups_aos` AS `a` ON `w`.`ao_channel_id`=`a`.`ao_channel_id` AND `w`.`team_id`=`a`.`team_id` ORDER BY REPLACE(`ao_display_name`, _UTF8MB4'The ', _UTF8MB4''),FIELD(`event_day_of_week`, _UTF8MB4'Sunday', _UTF8MB4'Monday', _UTF8MB4'Tuesday', _UTF8MB4'Wednesday', _UTF8MB4'Thursday', _UTF8MB4'Friday', _UTF8MB4'Saturday'),`event_time`;

