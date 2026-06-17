#!/usr/bin/env bash
set -euo pipefail

APP_ENV_VALUE="${APP_ENV:-dev}"
RUNTIME_URL="${DATABASE_URL:-}"
MIGRATION_URL="${DATABASE_MIGRATION_URL:-}"

# Local dev convenience: allow DATABASE_URL to be used for migrations.
if [ -z "$MIGRATION_URL" ] && [ "$APP_ENV_VALUE" = "dev" ]; then
  MIGRATION_URL="$RUNTIME_URL"
fi

# DB-less app: no runtime DB and no migration DB.
if [ -z "$RUNTIME_URL" ] && [ -z "$MIGRATION_URL" ]; then
  echo "No database URL set; skipping migrations."
  exit 0
fi

# DB app but migration URL missing.
if [ -z "$MIGRATION_URL" ] || [ "${MIGRATION_URL,,}" = "none" ]; then
  echo "DATABASE_URL is set, but DATABASE_MIGRATION_URL is missing; refusing to deploy without migrations."
  exit 1
fi

export DATABASE_MIGRATION_URL="$MIGRATION_URL"
export DATABASE_URL="$MIGRATION_URL"

uv run alembic upgrade head
uv run alembic current
