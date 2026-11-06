import os

# Unit tests do not open TiDB. They still call the schema helper, which refuses
# a missing DATABASE_SCHEMA.
os.environ.setdefault("DATABASE_SCHEMA", "f3ttown_test")
