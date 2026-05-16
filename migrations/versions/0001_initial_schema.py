"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-13

Creates all tables from the ORM baseline (photos, people, photo_people)
and the embeddings table with pgvector HNSW index.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "photos",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("storage_path", sa.String, nullable=False, unique=True),
        sa.Column("original_filename", sa.String, nullable=False),
        sa.Column("taken_at", sa.String, nullable=True),
        sa.Column("location_name", sa.String, nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("caption", sa.String, nullable=True),
        sa.Column("tags", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("activities", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("content_type", sa.String, nullable=True),
        sa.Column("subject_type", sa.String, nullable=True),
        sa.Column("primary_focus", sa.String, nullable=True),
        sa.Column("indoor_outdoor", sa.String, nullable=True),
        sa.Column("setting_type", sa.String, nullable=True),
        sa.Column("sharpness", sa.String, nullable=True),
        sa.Column("face_clarity_score", sa.Integer, nullable=True),
        sa.Column("caption_schema_version", sa.Integer, nullable=True),
        sa.Column("happiness_score", sa.Float, nullable=True),
        sa.Column("aesthetic_score", sa.Float, nullable=True),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("google_people", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("embed_schema_version", sa.Integer, nullable=True),
        sa.Column("scan_indexed_at", sa.String, nullable=True),
        sa.Column("caption_indexed_at", sa.String, nullable=True),
        sa.Column("vector_indexed_at", sa.String, nullable=True),
        sa.Column("face_indexed_at", sa.String, nullable=True),
        sa.Column("google_metadata_indexed_at", sa.String, nullable=True),
    )
    op.create_index("idx_photos_taken_at", "photos", ["taken_at"])
    op.create_index("idx_photos_content_type", "photos", ["content_type"])
    op.create_index("idx_photos_subject_type", "photos", ["subject_type"])
    op.create_index("idx_photos_setting_type", "photos", ["setting_type"])

    op.create_table(
        "people",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("family_id", sa.String, nullable=True),
    )

    op.create_table(
        "photo_people",
        sa.Column(
            "photo_id",
            sa.String,
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "person_id",
            sa.String,
            sa.ForeignKey("people.id"),
            primary_key=True,
        ),
        sa.Column("face_bbox", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
    )
    op.create_index("idx_photo_people_person", "photo_people", ["person_id"])

    op.create_table(
        "embeddings",
        sa.Column(
            "photo_id",
            sa.String,
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embed_model", sa.String, nullable=False),
        sa.Column("year", sa.Integer, nullable=True),
    )
    # Add vector column separately — pgvector type not in core SQLAlchemy.
    op.execute("ALTER TABLE embeddings ADD COLUMN embedding vector(1536) NOT NULL")
    op.execute(
        "CREATE INDEX embeddings_hnsw ON embeddings USING hnsw (embedding vector_cosine_ops)"
    )
    op.create_index("embeddings_year_idx", "embeddings", ["year"])


def downgrade() -> None:
    op.drop_table("embeddings")
    op.drop_table("photo_people")
    op.drop_table("people")
    op.drop_table("photos")
