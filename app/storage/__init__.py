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


_R2_VARS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def _require_r2_env() -> dict[str, str]:
    """Fail loud naming every unset R2_* var, instead of a late KeyError."""
    missing = [name for name in _R2_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"STORAGE_BACKEND=r2 but required env var(s) unset: {', '.join(missing)}. "
            "In the container, bridge them via the Worker's envVars."
        )
    return {name: os.environ[name] for name in _R2_VARS}


def _create_storage() -> Storage:
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "local":
        from ..config import get_settings
        from .local import LocalStorage

        return LocalStorage(get_settings().data_dir)
    if backend == "r2":
        from .r2 import R2Storage

        env = _require_r2_env()
        return R2Storage(
            account_id=env["R2_ACCOUNT_ID"],
            access_key=env["R2_ACCESS_KEY_ID"],
            secret_key=env["R2_SECRET_ACCESS_KEY"],
            bucket=env["R2_BUCKET"],
        )
    raise ValueError(f"Unknown STORAGE_BACKEND={backend!r}. Use 'local' or 'r2'.")


def reset_storage() -> None:
    """Reset singleton — for tests that change STORAGE_BACKEND."""
    global _storage
    _storage = None
