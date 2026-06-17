#!/usr/bin/env bash
set -euo pipefail

APP_ENV_VALUE="${APP_ENV:-production}"
DB_URL="${DATABASE_URL:-none}"
MIGRATION_URL="${DATABASE_MIGRATION_URL:-none}"

trim() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

is_none() {
  local value
  value="$(lower "$(trim "${1:-}")")"

  [ -z "$value" ] || [ "$value" = "none" ]
}

APP_ENV_VALUE="$(lower "$(trim "$APP_ENV_VALUE")")"
DB_URL="$(trim "$DB_URL")"
MIGRATION_URL="$(trim "$MIGRATION_URL")"

has_db_url=false
has_migration_url=false

if ! is_none "$DB_URL"; then
  has_db_url=true
fi

if ! is_none "$MIGRATION_URL"; then
  has_migration_url=true
fi

# Dev convenience:
# In dev, DATABASE_URL doubles as DATABASE_MIGRATION_URL.
if [ "$APP_ENV_VALUE" = "dev" ] && [ "$has_db_url" = true ] && [ "$has_migration_url" = false ]; then
  MIGRATION_URL="$DB_URL"
  has_migration_url=true
fi

# Case 1: no db_url, no migration_url
if [ "$has_db_url" = false ] && [ "$has_migration_url" = false ]; then
  echo "No database URL set; skipping migrations."
  exit 0
fi

# Case 2: db_url, no migration_url
if [ "$has_db_url" = true ] && [ "$has_migration_url" = false ]; then
  echo "DATABASE_URL is set, but DATABASE_MIGRATION_URL is missing or none."

  if [ "$APP_ENV_VALUE" = "dev" ]; then
    echo "Skipping migrations."
    exit 0
  fi

  echo "Refusing to deploy without migrations."
  exit 1
fi

# Case 3: no db_url, migration_url
if [ "$has_db_url" = false ] && [ "$has_migration_url" = true ]; then
  echo "DATABASE_MIGRATION_URL is set, but DATABASE_URL is missing or none."

  if [ "$APP_ENV_VALUE" = "dev" ]; then
    echo "Skipping migrations."
    exit 0
  fi

  echo "Refusing to deploy with inconsistent database config."
  exit 1
fi

# Case 4: db_url, migration_url
echo "DATABASE_URL and DATABASE_MIGRATION_URL are set; running migrations."

export DATABASE_MIGRATION_URL="$MIGRATION_URL"
export DATABASE_URL="$MIGRATION_URL"

PYTHON_BIN="${PYTHON_BIN:-/app/.venv/bin/python}"
ALEMBIC_CONFIG="${ALEMBIC_CONFIG:-/app/alembic.ini}"

"$PYTHON_BIN" -m alembic -c "$ALEMBIC_CONFIG" upgrade head
"$PYTHON_BIN" -m alembic -c "$ALEMBIC_CONFIG" current
