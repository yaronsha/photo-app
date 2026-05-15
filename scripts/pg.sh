#!/usr/bin/env bash
# Manage the local Postgres+pgvector Docker container.
# Usage: scripts/pg.sh [start|stop|restart|status|logs|psql|reset]
set -euo pipefail

CONTAINER="family-photos-pg"
IMAGE="pgvector/pgvector:pg16"

# Load env file: use ENV_FILE if set, otherwise .env
ENV_FILE="${ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

PG_USER="${PG_USER:-photos}"
PG_PASSWORD="${PG_PASSWORD:-photos}"
PG_DB="${PG_DB:-photos}"
PG_PORT="${PG_PORT:-5432}"

cmd="${1:-start}"

_running() {
  docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true
}

_exists() {
  docker inspect "$CONTAINER" &>/dev/null
}

case "$cmd" in
  start)
    if _running; then
      echo "Already running — $CONTAINER on port $PG_PORT"
      exit 0
    fi
    if _exists; then
      echo "Starting stopped container..."
      docker start "$CONTAINER"
    else
      echo "Creating $CONTAINER from $IMAGE..."
      docker run -d \
        --name "$CONTAINER" \
        -e POSTGRES_USER="$PG_USER" \
        -e POSTGRES_PASSWORD="$PG_PASSWORD" \
        -e POSTGRES_DB="$PG_DB" \
        -p "${PG_PORT}:5432" \
        -v "family-photos-pg-data:/var/lib/postgresql/data" \
        "$IMAGE"
    fi
    echo -n "Waiting for Postgres to accept connections"
    for i in $(seq 1 30); do
      if docker exec "$CONTAINER" pg_isready -U "$PG_USER" -d "$PG_DB" &>/dev/null; then
        echo " ready."
        break
      fi
      echo -n "."
      sleep 1
    done
    echo ""
    echo "DATABASE_URL=postgresql+psycopg://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}"
    echo "DATABASE_URL_DIRECT=postgresql+psycopg://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}"
    ;;

  stop)
    if _exists; then
      docker stop "$CONTAINER"
      echo "Stopped."
    else
      echo "Container $CONTAINER does not exist."
    fi
    ;;

  restart)
    "$0" stop || true
    "$0" start
    ;;

  status)
    if _running; then
      echo "RUNNING — $CONTAINER"
      docker exec "$CONTAINER" pg_isready -U "$PG_USER" -d "$PG_DB"
    elif _exists; then
      echo "STOPPED — $CONTAINER"
    else
      echo "NOT CREATED — $CONTAINER"
    fi
    ;;

  logs)
    docker logs --tail=50 -f "$CONTAINER"
    ;;

  psql)
    docker exec -it "$CONTAINER" psql -U "$PG_USER" -d "$PG_DB"
    ;;

  reset)
    echo "WARNING: This destroys all data in $CONTAINER and its volume."
    read -r -p "Type 'yes' to confirm: " confirm
    if [[ "$confirm" != "yes" ]]; then
      echo "Aborted."
      exit 1
    fi
    docker rm -f "$CONTAINER" 2>/dev/null || true
    docker volume rm family-photos-pg-data 2>/dev/null || true
    echo "Done. Run '$0 start' to recreate."
    ;;

  *)
    echo "Usage: $0 [start|stop|restart|status|logs|psql|reset]"
    exit 1
    ;;
esac
