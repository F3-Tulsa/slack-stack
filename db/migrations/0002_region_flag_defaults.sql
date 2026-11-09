UPDATE region_config SET email_enabled = 0 WHERE email_enabled IS NULL;
UPDATE region_config SET email_option_show = 0 WHERE email_option_show IS NULL;
UPDATE region_config SET editing_locked = 0 WHERE editing_locked IS NULL;
UPDATE region_config SET postie_format = 1 WHERE postie_format IS NULL;
UPDATE region_config SET strava_enabled = 1 WHERE strava_enabled IS NULL;
UPDATE region_config SET default_destination = 'ao_channel' WHERE default_destination IS NULL;
UPDATE region_config SET post_achievements_to_ao = 0 WHERE post_achievements_to_ao IS NULL;

ALTER TABLE region_config
  MODIFY email_enabled tinyint DEFAULT 0,
  MODIFY email_option_show tinyint DEFAULT 0,
  MODIFY editing_locked tinyint DEFAULT 0,
  MODIFY postie_format tinyint DEFAULT 1,
  MODIFY strava_enabled tinyint DEFAULT 1,
  MODIFY default_destination varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT 'ao_channel',
  MODIFY post_achievements_to_ao tinyint DEFAULT 0;
