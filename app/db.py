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


PHOTOS_ATTRIBUTE_COLUMNS: list[tuple[str, str]] = [
    ("activities", "TEXT"),
    ("content_type", "TEXT"),
    ("subject_type", "TEXT"),
    ("primary_focus", "TEXT"),
    ("indoor_outdoor", "TEXT"),
    ("setting_type", "TEXT"),
    ("sharpness", "TEXT"),
    ("face_clarity_score", "INTEGER"),
    ("caption_schema_version", "INTEGER"),
    ("embed_schema_version", "INTEGER"),
]


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
            activities          TEXT,
            content_type        TEXT,
            subject_type        TEXT,
            primary_focus       TEXT,
            indoor_outdoor      TEXT,
            setting_type        TEXT,
            sharpness           TEXT,
            face_clarity_score  INTEGER,
            caption_schema_version INTEGER,
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

    existing = {r[1] for r in conn.execute("PRAGMA table_info(photos)").fetchall()}
    for col, sqltype in PHOTOS_ATTRIBUTE_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE photos ADD COLUMN {col} {sqltype}")

    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_photos_content_type ON photos(content_type);
        CREATE INDEX IF NOT EXISTS idx_photos_subject_type ON photos(subject_type);
        CREATE INDEX IF NOT EXISTS idx_photos_setting_type ON photos(setting_type);
    """)
    conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("tags", "activities"):
        if field in d and d[field] and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
    return d
