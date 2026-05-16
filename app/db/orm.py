"""SQLAlchemy 2.0 ORM models — mirror the existing on-disk schema exactly.

Timestamps are stored as ISO strings (matches the existing data layout —
the old `sqlite3` layer wrote `datetime.isoformat()` strings into TIMESTAMP
columns; SQLite has no native datetime type, so we keep `String` here to
avoid any data migration).
"""
from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .types import JsonCol


class Base(DeclarativeBase):
    pass


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    storage_path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    taken_at: Mapped[str | None] = mapped_column(String, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    caption: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list | None] = mapped_column(JsonCol, nullable=True)
    activities: Mapped[list | None] = mapped_column(JsonCol, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_type: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_focus: Mapped[str | None] = mapped_column(String, nullable=True)
    indoor_outdoor: Mapped[str | None] = mapped_column(String, nullable=True)
    setting_type: Mapped[str | None] = mapped_column(String, nullable=True)
    sharpness: Mapped[str | None] = mapped_column(String, nullable=True)
    face_clarity_score: Mapped[int | None] = mapped_column(nullable=True)
    caption_schema_version: Mapped[int | None] = mapped_column(nullable=True)
    happiness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    aesthetic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    google_people: Mapped[list | None] = mapped_column(JsonCol, nullable=True)
    embed_schema_version: Mapped[int | None] = mapped_column(nullable=True)
    scan_indexed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    caption_indexed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    vector_indexed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    face_indexed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    google_metadata_indexed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_photos_taken_at", "taken_at"),
        Index("idx_photos_content_type", "content_type"),
        Index("idx_photos_subject_type", "subject_type"),
        Index("idx_photos_setting_type", "setting_type"),
    )


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    family_id: Mapped[str | None] = mapped_column(String, nullable=True)


class PhotoPerson(Base):
    __tablename__ = "photo_people"

    photo_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    person_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("people.id"),
        primary_key=True,
    )
    face_bbox: Mapped[list | None] = mapped_column(JsonCol, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("idx_photo_people_person", "person_id"),
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    photo_id: Mapped[str] = mapped_column(
        String, ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    embed_model: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
