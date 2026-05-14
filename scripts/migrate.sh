#!/usr/bin/env bash
# Alembic migration runner.
# Usage: scripts/migrate.sh [upgrade [rev]|downgrade [rev]|status|history|revision <msg>]
#
# Reads DATABASE_URL_DIRECT (preferred) or DATABASE_URL from env / .env file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Load .env if present (won't override existing env vars).
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Validate a DB URL is available.
DB_URL="${DATABASE_URL_DIRECT:-${DATABASE_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "Error: set DATABASE_URL_DIRECT (or DATABASE_URL) in .env or environment." >&2
  exit 1
fi

cmd="${1:-status}"
shift || true

case "$cmd" in
  upgrade)
    rev="${1:-head}"
    echo "Upgrading to: $rev"
    uv run alembic upgrade "$rev"
    ;;

  downgrade)
    rev="${1:--1}"
    echo "Downgrading to: $rev"
    uv run alembic downgrade "$rev"
    ;;

  status|current)
    uv run alembic current
    ;;

  history)
    uv run alembic history --verbose
    ;;

  revision)
    msg="${1:?Usage: migrate.sh revision <message>}"
    uv run alembic revision --autogenerate -m "$msg"
    echo "New revision created in migrations/versions/. Review before committing."
    ;;

  *)
    echo "Usage: $0 [upgrade [rev]|downgrade [rev]|status|history|revision <msg>]"
    exit 1
    ;;
esac
