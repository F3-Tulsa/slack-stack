# Schema migrations

`python db/migrate.py --schema f3ttown_test` applies `db/migrations/NNNN_slug.sql` in order and records each file in `schema_migrations`.

The directory is empty on purpose. `0001_baseline.sql` is generated from a rehearsed consolidated schema, not from the current four-schema layout. See `db/INVENTORY.md`.

The runner refuses a schema ending in `_prod` unless `--allow-prod` is passed, and it refuses `f3scissortail_*` and `weaselbot_*`. Nothing in `deploy.sh` or `deploy.yml` calls it, so merging this branch does not migrate prod.
