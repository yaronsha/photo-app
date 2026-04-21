import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import get_settings


def get_conn() -> sqlite3.Connection:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS photos (
            id                  TEXT PRIMARY KEY,
            storage_path        TEXT NOT NULL UNIQUE,
            original_filename   TEXT NOT NULL,
            taken_at            TIMESTAMP,
            location_name       TEXT,
            lat                 REAL,
            lng                 REAL,
            caption             TEXT,
            tags                TEXT,
            happiness_score     REAL,
            aesthetic_score     REAL,
            description         TEXT,
            google_people       TEXT,
            scan_indexed_at     TIMESTAMP,
            caption_indexed_at  TIMESTAMP,
            vector_indexed_at   TIMESTAMP,
            face_indexed_at     TIMESTAMP,
            google_metadata_indexed_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS people (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            family_id  TEXT
        );

        CREATE TABLE IF NOT EXISTS photo_people (
            photo_id    TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
            person_id   TEXT NOT NULL REFERENCES people(id),
            face_bbox   TEXT,
            confidence  REAL,
            PRIMARY KEY (photo_id, person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_photos_taken_at ON photos(taken_at);
        CREATE INDEX IF NOT EXISTS idx_photo_people_person ON photo_people(person_id);
    """)
    conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("tags") and isinstance(d["tags"], str):
        try:
            d["tags"] = json.loads(d["tags"])
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
    return d
