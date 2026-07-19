#!/bin/sh
set -eu

python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    print("DATABASE_URL is required", file=sys.stderr)
    sys.exit(1)

engine = create_engine(database_url, pool_pre_ping=True)
timeout_seconds = int(os.environ.get("DB_WAIT_TIMEOUT", "120"))
deadline = time.time() + timeout_seconds
attempt = 0

while True:
    attempt += 1
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Database is ready")
        break
    except Exception as exc:
        if time.time() >= deadline:
            print(f"Database did not become ready within {timeout_seconds}s: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Waiting for database (attempt {attempt}): {exc}")
        time.sleep(2)
PY

python migration_runner.py upgrade
python migrations/migrate_csv.py

exec "$@"