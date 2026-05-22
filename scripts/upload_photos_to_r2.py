#!/usr/bin/env python3
"""Upload local photos/thumbs/sidecars to Cloudflare R2.

Reads photo keys from local SQLite (post-0002: keys already in `photos/...` form).
Idempotent — skips keys already present in R2. Safe to re-run after interruption.

Usage:
    ENV_FILE=.env.local STORAGE_BACKEND=r2 R2_BUCKET=family-photos-prod \\
    R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... \\
    uv run python scripts/upload_photos_to_r2.py [--dry-run] [--workers N]
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_env_file = os.environ.get("ENV_FILE")
if _env_file:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / _env_file, override=False)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.orm import Photo
from app.storage import get_storage
from app.storage.r2 import R2Storage


def _collect_keys(settings) -> list[str]:
    keys: list[str] = []

    engine = create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
    )
    with Session(engine) as s:
        photo_keys = [row[0] for row in s.execute(select(Photo.storage_path))]

    # Validate all keys are post-0002 (relative, not absolute paths).
    bad = [k for k in photo_keys if k.startswith("/")]
    if bad:
        sys.exit(
            f"Error: {len(bad)} rows still have absolute paths (pre-0002).\n"
            f"  Example: {bad[0]}\n"
            f"  Run Alembic migration 0002 against local SQLite first."
        )
    print(f"Photos (from DB):  {len(photo_keys)}")
    keys.extend(photo_keys)

    for prefix in ("thumbs", "sidecars"):
        d = settings.data_dir / prefix
        if d.exists():
            dir_keys = [f"{prefix}/{p.name}" for p in sorted(d.iterdir()) if p.is_file()]
            print(f"{prefix.capitalize()} (from disk): {len(dir_keys)}")
            keys.extend(dir_keys)
        else:
            print(f"{prefix.capitalize()} dir not found, skipping: {d}")

    return keys


def _upload_one(
    key: str,
    data_dir: Path,
    r2: R2Storage,
    dry_run: bool,
) -> str:
    """Returns: 'uploaded' | 'skipped' | 'missing' | 'would_upload'"""
    src = data_dir / key
    if not src.exists():
        return "missing"
    if r2.exists(key):
        return "skipped"
    if dry_run:
        return "would_upload"
    mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    r2.write_bytes(key, src.read_bytes(), content_type=mime)
    return "uploaded"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    if os.getenv("STORAGE_BACKEND") != "r2":
        sys.exit("Error: set STORAGE_BACKEND=r2")

    settings = get_settings()
    r2 = get_storage()
    if not isinstance(r2, R2Storage):
        sys.exit("Error: storage backend is not R2")

    keys = _collect_keys(settings)
    total = len(keys)
    print(f"\nTotal: {total}" + ("  [DRY RUN — no uploads]" if args.dry_run else ""))
    print()

    counts: dict[str, int] = {"uploaded": 0, "skipped": 0, "missing": 0, "would_upload": 0}
    lock = threading.Lock()
    done = 0

    def _task(key: str) -> None:
        nonlocal done
        status = _upload_one(key, settings.data_dir, r2, args.dry_run)
        with lock:
            counts[status] += 1
            done += 1
            if done % 250 == 0 or done == total:
                if args.dry_run:
                    line = (
                        f"  {done}/{total}  "
                        f"would_upload={counts['would_upload']}  "
                        f"skipped={counts['skipped']}  "
                        f"missing={counts['missing']}"
                    )
                else:
                    line = (
                        f"  {done}/{total}  "
                        f"uploaded={counts['uploaded']}  "
                        f"skipped={counts['skipped']}  "
                        f"missing={counts['missing']}"
                    )
                print(line, end="\r", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(_task, keys))

    print()
    print()
    if args.dry_run:
        print(
            f"Dry run: would_upload={counts['would_upload']}  "
            f"already_in_r2={counts['skipped']}  "
            f"missing_locally={counts['missing']}"
        )
    else:
        print(
            f"Done:  uploaded={counts['uploaded']}  "
            f"skipped={counts['skipped']}  "
            f"missing={counts['missing']}"
        )
    if counts["missing"]:
        print(
            f"\nWARNING: {counts['missing']} keys have no local file. "
            "Investigate before prod cutover."
        )


if __name__ == "__main__":
    main()
