# Migration

## Import from the old F3 Nation database

Use this only for a region that still has the old regional schema and shared QSignups tables. Tulsa is already on `f3ttown_prod` and does not use this path.

Use `.env.deploy.<stage>`. It has `DATABASE_*`, `F3_REGION_NAME`, and `F3_REGION_SLACK_TEAM_ID`. The migration env files have `TARGET_*` only, so they need `--prefix TARGET`.

One connection reads the old schemas and the new one, so restore the old schemas onto the target server first. The shared QSignups schema holds other regions' tokens and `google_auth_data`. Drop that restored copy after the import.

1. `python db/migrate.py --env-file .env.deploy.<stage> --to 1` creates the empty baseline and records version 1. It does not seed.
2. `python migration/legacy_import.py --env-file .env.deploy.<stage> --source-schema <old regional schema> --qsignups-schema <old qsignups schema> --team-id <slack team> --target-schema <region>_<stage>` copies rows. The target must be the schema derived from the env file and must record exactly version 1. The importer does not create or alter tables. It skips token columns, including `google_auth_data`, and refuses a target table that already has rows. A missing source schema or table is an error.
3. `python db/fresh_install.py --env-file .env.deploy.<stage>` applies later files and seeds defaults only when those tables are empty. It keeps an imported `qsignups_regions` row. Later schema changes use `db/migrate.py`, not another seed. A prod stage passes `--allow-prod` to steps 1 and 3. Tokens stay empty; the Lambda cold start writes them. Do not encrypt them during the import.

4. Images are a separate operator step, after the rows are in place. `python migration/migrate_images.py --env <stage>` reads `migration/.env.migration.<stage>` and `IMAGE_S3_BUCKET`. It copies backblast images into the region's bucket. It does not change the schema.

5. Achievements are a separate operator step. Leave the Award Achievements schedule disabled. Run `python migration/rehearsal_reconcile.py --env <stage> --schemas <region>_<stage> --all-attendance --allow-revoke`, then the same command with `--dry-run` until it reports grants 0 and revokes 0. Then enable the schedule. Legacy award rows are not the source of truth. The new counts will differ.

The importer is tested in CI against the old QSignups DDL in `qsignups/db` (`tables/` plus scripts `001`–`007`) and one row each of `users`, `aos`, `beatdowns`, and `bd_attendance`. No real PAX data. It has not been run against a live national database. The national RDS is gone.

`migration/convert_to_baseline.py --compare` creates and drops a scratch database named `compare_scratch_<id>_<stage>` on the same server. The id is new every run. The stage suffix keeps the name inside that stage user's grant.

Tulsa's own move is history in [docs/MIGRATION.md](../docs/MIGRATION.md). Do not run `migration/migrate_data.py` against Tulsa.
