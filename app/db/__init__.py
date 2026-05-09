"""Database layer — SQLAlchemy 2.0 ORM, lazy engine, sqlite/postgres-ready.

Exports the public surface used by the rest of the app:
- get_engine / dispose_engines      — engine cache (test-friendly)
- SessionLocal / get_session        — Session factory + context manager
- db_session                        — FastAPI dependency
- init_schema                       — DDL bootstrap
- Base, Photo, Person, PhotoPerson  — ORM models
"""
from .engine import dispose_engines, get_engine
from .orm import Base, Person, Photo, PhotoPerson
from .schema import PHOTOS_ATTRIBUTE_COLUMNS, init_schema
from .session import SessionLocal, db_session, get_session

__all__ = [
    "Base",
    "PHOTOS_ATTRIBUTE_COLUMNS",
    "Person",
    "Photo",
    "PhotoPerson",
    "SessionLocal",
    "db_session",
    "dispose_engines",
    "get_engine",
    "get_session",
    "init_schema",
]
