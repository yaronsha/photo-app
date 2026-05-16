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
migration is idempotent. The migration aborts loud if any row's path cannot
be parsed back to a ``photos/...`` key, so a partial rewrite cannot leak
through.

Deriving the key
================

The operator must supply the absolute prefix to strip via the environment
variable ``STORAGE_MIGRATION_PREFIX``. Every row must start with this
prefix; otherwise the migration aborts. This avoids ambiguity in paths that
contain ``/photos/`` more than once (e.g. ``/home/me/photos/app/photos/...``)
and makes the rewrite a pure string operation rather than a heuristic.

Example::

    STORAGE_MIGRATION_PREFIX=/Users/yaron/family-photos-app/  scripts/migrate.sh upgrade head

If ``STORAGE_MIGRATION_PREFIX`` is unset and the table contains any
absolute-path rows, the migration aborts with a message naming the longest
common prefix it observed, which the operator can copy verbatim into the
env var.

After running this migration, the caller is responsible for ensuring the
files referenced by the new keys exist at the storage root. For local dev
that means physically moving the on-disk ``photos/`` tree into
``data_dir/photos/`` (one-time, see ``docs/migration/runbook.md``).
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _longest_common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    s1, s2 = min(strings), max(strings)
    i = 0
    while i < len(s1) and i < len(s2) and s1[i] == s2[i]:
        i += 1
    return s1[:i]


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, storage_path FROM photos")).fetchall()

    absolute_rows = [(pid, sp) for pid, sp in rows if sp and sp.startswith("/")]
    already_key = sum(1 for _, sp in rows if sp and not sp.startswith("/"))

    if not absolute_rows:
        print(f"0002: nothing to rewrite, already-key {already_key}")
        return

    prefix = os.environ.get("STORAGE_MIGRATION_PREFIX", "").rstrip("/") + "/"
    if prefix == "/":
        # Compute the longest common prefix so the operator gets a concrete value.
        common = _longest_common_prefix([sp for _, sp in absolute_rows])
        # Trim to the last "/" so we don't half-cut a filename component.
        if "/" in common:
            common = common[: common.rfind("/") + 1]
        raise RuntimeError(
            "STORAGE_MIGRATION_PREFIX is not set and "
            f"{len(absolute_rows)} row(s) still have absolute storage_path. "
            f"Observed longest common prefix: {common!r}. "
            "Re-run with that as STORAGE_MIGRATION_PREFIX, "
            "e.g. STORAGE_MIGRATION_PREFIX="
            f"{common.rstrip('/')!r} scripts/migrate.sh upgrade head"
        )

    rewritten = 0
    for pid, sp in absolute_rows:
        if not sp.startswith(prefix):
            raise RuntimeError(
                f"Cannot derive key for photo id={pid!r}: storage_path={sp!r} "
                f"does not start with STORAGE_MIGRATION_PREFIX={prefix!r}. "
                "Investigate this row before retrying."
            )
        key = sp[len(prefix):]
        if not key.startswith("photos/"):
            raise RuntimeError(
                f"Cannot derive key for photo id={pid!r}: stripped value "
                f"{key!r} does not start with 'photos/'. The supplied prefix "
                f"({prefix!r}) is probably wrong."
            )
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
