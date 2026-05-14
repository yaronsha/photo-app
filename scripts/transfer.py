#!/usr/bin/env python3
"""Transfer data between SQLite and Postgres (both directions).

Usage:
    uv run python scripts/transfer.py sqlite-to-pg [--sqlite PATH] [--pg URL] [--batch N]
    uv run python scripts/transfer.py pg-to-sqlite [--sqlite PATH] [--pg URL] [--batch N]

Tables transferred: photos, people, photo_people.
The embeddings table is Postgres-only (pgvector) and is never transferred.

JSON columns:
  - SQLite stores them as TEXT strings.
  - Postgres stores them as JSONB.
  The script serialises/deserialises automatically in both directions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Columns that are JSON in Postgres (JSONB) but TEXT in SQLite.
JSON_COLUMNS: dict[str, list[str]] = {
    "photos": ["tags", "activities", "google_people"],
    "people": [],
    "photo_people": ["face_bbox"],
}

# Transfer order respects FK dependencies.
TABLE_ORDER = ["photos", "people", "photo_people"]


def _pg_url() -> str:
    url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL") or ""
    if not url:
        raise SystemExit(
            "Error: set DATABASE_URL_DIRECT or DATABASE_URL in env/.env"
        )
    return url


def _sqlite_url(path: str | None) -> str:
    if path:
        return f"sqlite:///{path}"
    # Fall back to config-derived default.
    from app.config import get_settings
    settings = get_settings()
    return f"sqlite:///{settings.db_path}"


def _col_names(conn, table: str) -> list[str]:
    result = conn.execute(text(f"SELECT * FROM {table} LIMIT 0"))
    return list(result.keys())


def _to_json_text(value) -> str | None:
    """Serialise Python object → JSON string for SQLite storage."""
    if value is None:
        return None
    if isinstance(value, str):
        return value  # already serialised
    return json.dumps(value)


def _from_json_text(value) -> object:
    """Deserialise JSON string from SQLite → Python object for Postgres."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def transfer(src_engine, dst_engine, direction: str, batch_size: int) -> None:
    sqlite_to_pg = direction == "sqlite-to-pg"

    with src_engine.connect() as src, dst_engine.connect() as dst:
        for table in TABLE_ORDER:
            json_cols = JSON_COLUMNS.get(table, [])

            total = src.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"{table}: {total} rows to transfer")

            # Read column names from source.
            cols = _col_names(src, table)
            col_list = ", ".join(cols)
            placeholders = ", ".join(f":{c}" for c in cols)

            offset = 0
            transferred = 0
            while True:
                rows = src.execute(
                    text(f"SELECT {col_list} FROM {table} LIMIT :limit OFFSET :offset"),
                    {"limit": batch_size, "offset": offset},
                ).mappings().all()

                if not rows:
                    break

                batch = []
                for row in rows:
                    record = dict(row)
                    for col in json_cols:
                        if col in record:
                            if sqlite_to_pg:
                                record[col] = _from_json_text(record[col])
                            else:
                                record[col] = _to_json_text(record[col])
                    batch.append(record)

                # Upsert: delete-then-insert in a transaction avoids dialect-specific
                # ON CONFLICT syntax differences between SQLite and Postgres.
                with dst.begin():
                    for record in batch:
                        pk_col = "id" if table != "photo_people" else None
                        if pk_col and pk_col in record:
                            dst.execute(
                                text(f"DELETE FROM {table} WHERE id = :id"),
                                {"id": record["id"]},
                            )
                        elif table == "photo_people":
                            dst.execute(
                                text(
                                    "DELETE FROM photo_people "
                                    "WHERE photo_id = :photo_id AND person_id = :person_id"
                                ),
                                {
                                    "photo_id": record["photo_id"],
                                    "person_id": record["person_id"],
                                },
                            )
                        dst.execute(
                            text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"),
                            record,
                        )

                transferred += len(batch)
                offset += batch_size
                print(f"  {transferred}/{total}", end="\r", flush=True)

            print(f"  {transferred}/{total} done.    ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("direction", choices=["sqlite-to-pg", "pg-to-sqlite"])
    parser.add_argument("--sqlite", help="Path to SQLite file (default: from config.json)")
    parser.add_argument("--pg", help="Postgres URL (default: DATABASE_URL_DIRECT or DATABASE_URL env)")
    parser.add_argument("--batch", type=int, default=500, help="Rows per batch (default: 500)")
    args = parser.parse_args()

    sqlite_url = _sqlite_url(args.sqlite)
    pg_url = args.pg or _pg_url()

    print(f"Direction: {args.direction}")
    print(f"SQLite:    {sqlite_url}")
    print(f"Postgres:  {pg_url.split('@')[-1]}")  # hide credentials
    print()

    sqlite_engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
    )
    pg_engine = create_engine(pg_url)

    if args.direction == "sqlite-to-pg":
        transfer(sqlite_engine, pg_engine, "sqlite-to-pg", args.batch)
    else:
        transfer(pg_engine, sqlite_engine, "pg-to-sqlite", args.batch)

    print("\nTransfer complete.")


if __name__ == "__main__":
    main()
