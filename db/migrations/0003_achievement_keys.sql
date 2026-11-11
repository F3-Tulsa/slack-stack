-- Unique achievement codes, and an index for award lookups by PAX.
-- achievements_list is first, so a duplicate-code failure leaves nothing applied.
-- MySQL has no ADD KEY IF NOT EXISTS. If the first statement applies and the
-- second fails, fix the second by hand before recording this file.

ALTER TABLE `achievements_list`
  ADD UNIQUE KEY `uniq_code` (`code`);

ALTER TABLE `achievements_awarded`
  ADD KEY `idx_pax_id` (`pax_id`);
