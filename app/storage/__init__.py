"""Storage backend factory.

Select backend via STORAGE_BACKEND env var:
  local  — local filesystem under data_dir (default, rollback path)
  r2     — Cloudflare R2 via boto3 S3-compatible API
"""
from __future__ import annotations

import os

from .base import Storage

_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = _create_storage()
    return _storage


def _create_storage() -> Storage:
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "local":
        from ..config import get_settings
        from .local import LocalStorage

        return LocalStorage(get_settings().data_dir)
    if backend == "r2":
        from .r2 import R2Storage

        return R2Storage(
            account_id=os.environ["R2_ACCOUNT_ID"],
            access_key=os.environ["R2_ACCESS_KEY_ID"],
            secret_key=os.environ["R2_SECRET_ACCESS_KEY"],
            bucket=os.environ["R2_BUCKET"],
        )
    raise ValueError(f"Unknown STORAGE_BACKEND={backend!r}. Use 'local' or 'r2'.")


def reset_storage() -> None:
    """Reset singleton — for tests that change STORAGE_BACKEND."""
    global _storage
    _storage = None
