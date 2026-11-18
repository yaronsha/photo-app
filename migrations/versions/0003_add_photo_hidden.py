"""add photos.hidden_at / photos.hidden_by for admin hide

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18

Admins can hide a photo from the web UI. A photo is hidden when
``hidden_at`` is not NULL; ``hidden_by`` records the admin's email.
Both columns are nullable, so existing rows stay visible.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("hidden_at", sa.String, nullable=True))
    op.add_column("photos", sa.Column("hidden_by", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "hidden_by")
    op.drop_column("photos", "hidden_at")
