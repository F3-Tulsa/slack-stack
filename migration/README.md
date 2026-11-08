# Migration

## Import from the old F3 Nation database

Use this only for a region that still has the old regional schema and shared QSignups tables. Tulsa is already on `f3ttown_prod` and does not use this path.

1. `python db/migrate.py --env-file <file> --to 1` creates the empty baseline and records version 1. It does not seed.
2. `python migration/legacy_import.py --env-file <file> --source-schema <old regional schema> --qsignups-schema <old qsignups schema> --team-id <slack team> --target-schema <region>_<stage>` copies rows. The target must be the schema derived from the env file and must record exactly version 1. The importer does not create or alter tables. It skips token columns, including `google_auth_data`, and refuses a target table that already has rows.
3. `python db/fresh_install.py --env-file <file>` applies later files and seeds defaults only when those tables are empty. It keeps an imported `qsignups_regions` row. Later schema changes use `db/migrate.py`, not another seed.

The importer is tested against a schema-only fixture (one fake QSignups region and one feature row, no PAX). It has not been run against a live national database. The national RDS is gone.

Tulsa's own move is history in [docs/MIGRATION.md](../docs/MIGRATION.md). Do not run `migration/migrate_data.py` against Tulsa.
