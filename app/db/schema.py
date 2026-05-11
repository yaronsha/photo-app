"""init_schema — DDL bootstrap.

`Base.metadata.create_all` covers the canonical schema. The legacy
ALTER-loop adds any `PHOTOS_ATTRIBUTE_COLUMNS` that may be missing on
older field DBs that pre-date a column being added to the model. Keep
the loop for one release.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .engine import get_engine
from .orm import Base

# Columns historically ALTERed-in on old DBs. Kept for one release.
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


def init_schema(engine: Engine | None = None) -> None:
    eng = engine or get_engine()
    Base.metadata.create_all(eng)

    # Backstop ALTERs for older sqlite field DBs only.
    if eng.dialect.name != "sqlite":
        return

    with eng.begin() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(photos)")).fetchall()
        }
        for col, sqltype in PHOTOS_ATTRIBUTE_COLUMNS:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE photos ADD COLUMN {col} {sqltype}"))
