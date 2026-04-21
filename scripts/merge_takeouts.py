#!/usr/bin/env python3
"""
Merge Google Takeout folders into photos/ directory.

- Deduplicates by SHA256 content hash (same algorithm as scan.py)
- Organizes into photos/YYYY/ using photoTakenTime from sidecar JSON
- Saves sidecar JSON to data/sidecars/{photo_id}.json for later indexing

Usage:
    python scripts/merge_takeouts.py <folder> [<folder> ...] [--dry-run]

    # Initial import
    python scripts/merge_takeouts.py ~/Downloads/Takeout ~/Downloads/"Takeout 2" ...

    # Add new photos later — only pass the new folder
    python scripts/merge_takeouts.py ~/Downloads/"Takeout 11"
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

ACCEPTED_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".avi", ".gif", ".webp"}


def sha256_id(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def find_sidecar(photo_path: Path) -> Path | None:
    """
    Find JSON sidecar for a photo. Google Takeout uses two naming patterns:
      1. photo.jpg.supplemental-metadata.json
      2. {uuid_truncated}.json where json stem = photo stem minus last char
         e.g. photo: abc123def.jpg → sidecar: abc123de.json
    """
    supp = photo_path.parent / (photo_path.name + ".supplemental-metadata.json")
    if supp.exists():
        return supp

    plain = photo_path.parent / (photo_path.name + ".json")
    if plain.exists():
        return plain

    stem = photo_path.stem
    if len(stem) > 1:
        trunc_json = photo_path.parent / (stem[:-1] + ".json")
        if trunc_json.exists():
            return trunc_json

    return None


def year_from_sidecar(data: dict) -> int | None:
    ts = data.get("photoTakenTime", {}).get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).year
        except Exception:
            pass
    return None


def year_from_folder(folder_name: str) -> int | None:
    if folder_name.startswith("Photos from "):
        try:
            return int(folder_name.split()[-1])
        except ValueError:
            pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Merge Google Takeout folders into photos/")
    parser.add_argument("folders", nargs="+", type=Path, help="Takeout/Google Photos folders to merge")
    parser.add_argument("--dry-run", action="store_true", help="Preview without copying")
    args = parser.parse_args()

    photos_dir = PROJECT_ROOT / "photos"
    sidecars_dir = PROJECT_ROOT / "data" / "sidecars"

    if not args.dry_run:
        photos_dir.mkdir(parents=True, exist_ok=True)
        sidecars_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    merged = skipped_dupe = no_sidecar = 0

    for folder in args.folders:
        if not folder.exists():
            print(f"skip (not found): {folder}")
            continue

        print(f"\n→ {folder}")
        folder_count = 0

        for photo_path in sorted(folder.rglob("*")):
            if not photo_path.is_file():
                continue
            if photo_path.suffix.lower() not in ACCEPTED_EXTS:
                continue

            photo_id = sha256_id(photo_path)

            if photo_id in seen:
                skipped_dupe += 1
                continue
            seen.add(photo_id)

            sidecar_data: dict | None = None
            sidecar_path = find_sidecar(photo_path)
            if sidecar_path:
                try:
                    sidecar_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            else:
                no_sidecar += 1

            year = (
                (year_from_sidecar(sidecar_data) if sidecar_data else None)
                or year_from_folder(photo_path.parent.name)
                or "unknown"
            )

            dest_dir = photos_dir / str(year)
            dest_name = photo_path.name
            dest_path = dest_dir / dest_name

            # collision: same name, different content
            if dest_path.exists() and not args.dry_run:
                dest_name = f"{photo_id}_{photo_path.name}"
                dest_path = dest_dir / dest_name

            if args.dry_run:
                print(f"  [dry] {photo_path.name} → photos/{year}/{dest_name}")
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(photo_path, dest_path)
                if sidecar_data:
                    (sidecars_dir / f"{photo_id}.json").write_text(
                        json.dumps(sidecar_data, ensure_ascii=False, indent=2)
                    )

            merged += 1
            folder_count += 1

        print(f"  {folder_count} files")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done:")
    print(f"  {merged} merged")
    print(f"  {skipped_dupe} duplicates skipped")
    print(f"  {no_sidecar} files had no sidecar JSON")


if __name__ == "__main__":
    main()
