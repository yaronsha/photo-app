"""rewrite storage_path from absolute filesystem path to backend-agnostic key

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16

Phase 2 single-column variant. Pre-existing photo rows store
`Photo.storage_path` as an absolute filesystem path
(e.g. ``/Users/yaron/family-photos-app/photos/2014/img.jpg``). The storage
abstraction expects a key (``photos/2014/img.jpg``) that the active backend
resolves — ``LocalStorage`` joins it to ``data_dir`` and ``R2Storage`` treats
it as an S3 object key.

This migration rewrites every existing ``storage_path`` value to the key
form. Rows already in key form (no leading ``/``) are left untouched, so the
migration is idempotent.

After running this migration, the caller is responsible for ensuring the
files referenced by the new keys exist at the storage root. For local dev
that means physically moving the on-disk ``photos/`` tree into
``data_dir/photos/`` (one-time, see ``docs/migration/runbook.md``).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, storage_path FROM photos")).fetchall()

    rewritten = 0
    already_key = 0

    for pid, sp in rows:
        if sp is None:
            continue
        if not sp.startswith("/"):
            already_key += 1
            continue
        idx = sp.rfind("/photos/")
        if idx < 0:
            raise RuntimeError(
                f"Cannot derive key for photo id={pid!r}: storage_path={sp!r} "
                "has no '/photos/' segment. Aborting migration — investigate "
                "manually before retrying."
            )
        key = sp[idx + 1:]
        conn.execute(
            sa.text("UPDATE photos SET storage_path = :k WHERE id = :i"),
            {"k": key, "i": pid},
        )
        rewritten += 1

    remaining = conn.execute(
        sa.text("SELECT COUNT(*) FROM photos WHERE storage_path LIKE '/%'")
    ).scalar()
    if remaining:
        raise RuntimeError(
            f"{remaining} rows still have absolute storage_path after rewrite — "
            "migration aborted; rollback recommended."
        )

    print(f"0002: rewrote {rewritten}, already-key {already_key}")


def downgrade() -> None:
    # Downgrade is impossible without knowing the original absolute prefix.
    # If you need to revert, restore from the pre-upgrade DB backup.
    raise NotImplementedError(
        "Cannot reverse 0002: the original absolute path prefix is not recorded. "
        "Restore from backup taken before the upgrade."
    )
