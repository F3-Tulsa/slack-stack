# Schema migrations

`python db/migrate.py --env-file .env.deploy.test` applies `NNNN_slug.sql` in order. The schema is `${F3_REGION_NAME}_<stage>`. The stage is the suffix of the env file name. `--prefix TARGET` reads `TARGET_*` instead of `DATABASE_*`. CI uses `--from-environment --stage <stage>`, and `STAGE` must match.

`--allow-prod` is required when the stage is `prod`.

`--check` connects and reports. It exits 1 when a file is pending or a checksum changed, and it does not write.

`--mark-applied N` records files `0001` through `N` without executing them, after checking that each `CREATE TABLE` and `CREATE VIEW` names a table that already exists. It prints the plan unless `--yes` is passed. It refuses when `schema_migrations` already has a row.

SQL files are split on semicolons. The splitter assumes the default `sql_mode`, so backslash escapes quotes. It keeps `/*! */`, `/*T! */`, and `/*+ */` comments, because MySQL and TiDB execute those. A line that starts with `DELIMITER`, in any case, is rejected. A column that is literally named delimiter at the start of a line has to be backticked. Checksums use LF and ignore a leading BOM.

`0001_baseline.sql` is the rehearsed consolidated schema. It creates tables and views only. The runner still creates `schema_migrations` itself. Nothing in `deploy.sh` or `deploy.yml` calls the runner.

`0002_region_flag_defaults.sql` gives Slackblast's flag columns server defaults and fills NULLs. It is not applied to `f3ttown_test` or `f3ttown_prod` until an operator runs the runner there. Tulsa's existing row already has those values, so the backfill does not change it.

`python db/fresh_install.py --env-file migration/.env.migration.test` creates a new region's schema, applies pending files, and seeds defaults only when the report and achievement tables are empty. It refuses `f3ttown_test` and `f3ttown_prod`. `F3_REGION_SLACK_TEAM_ID` is required. `--timezone` overrides `F3_TIMEZONE`, which otherwise defaults to `America/Chicago`. The Slack token is left empty for the Lambda cold start.

`CREATE TABLE IF NOT EXISTS` lets a failed first apply be retried, but it also lets a plain apply record `0001` on a schema that already has different tables. The runner refuses that. Adopt an existing schema with `--mark-applied`. A failed fresh install that holds no data is dropped and run again.
