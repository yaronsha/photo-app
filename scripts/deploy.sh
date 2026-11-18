#!/usr/bin/env bash
# Production deploy: run DB migrations, then deploy the Worker + container.
#
# Meant as the Workers Builds *deploy command* for the production branch:
#     bash scripts/deploy.sh
# (Preview builds use the separate Preview command, so they never migrate.)
#
# Needs the build secret DATABASE_URL_DIRECT (direct Postgres on :5432, not
# the :6543 pooler). If it's missing we fail instead of silently skipping, so
# new code never goes live against an old schema. If a migration fails, the
# deploy is aborted and the previous version keeps serving.
#
# Migrations run *before* the new code is live, so they must stay compatible
# with the code that is still running (add columns/tables; drop only in a
# later release).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${DATABASE_URL_DIRECT:-}" ]]; then
  echo "deploy: DATABASE_URL_DIRECT is not set; refusing to deploy without migrating." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  python3 -m pip install --quiet --user uv
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "deploy: running migrations"
scripts/migrate.sh upgrade head

echo "deploy: wrangler deploy"
npx wrangler deploy
