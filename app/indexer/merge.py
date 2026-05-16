import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from ..config import get_settings
from ..db import Photo, get_session
from ..storage import get_storage

ACCEPTED_EXTS = {".jpg", ".jpeg", ".png", ".heic"}


def _sha256_id(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _find_sidecar(photo_path: Path) -> Path | None:
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


def _year_from_sidecar(data: dict) -> int | None:
    ts = data.get("photoTakenTime", {}).get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).year
        except Exception:
            pass
    return None


def _year_from_folder(folder_name: str) -> int | None:
    if folder_name.startswith("Photos from "):
        try:
            return int(folder_name.split()[-1])
        except ValueError:
            pass
    return None


def _load_seen_ids(db_path: Path) -> set[str]:
    """Read existing photo IDs from the DB, if any.

    The merge step is happy if the photos table is missing or the file
    isn't a populated DB yet — that just means everything is unseen.
    """
    if not db_path.exists():
        return set()
    try:
        with get_session() as session:
            rows = session.execute(select(Photo.id)).all()
            return {r[0] for r in rows}
    except OperationalError:
        # Table absent on a freshly-touched DB — treat as no prior data.
        return set()


def run_merge(folders: list[Path], dry_run: bool = False) -> dict:
    settings = get_settings()
    storage = get_storage()

    seen: set[str] = _load_seen_ids(settings.db_path)

    merged = skipped_dupe = no_sidecar = 0
    items: list[tuple[str, Path]] = []

    for folder in folders:
        if not folder.exists():
            print(f"skip (not found): {folder}")
            continue

        print(f"\n→ {folder}")
        folder_count = folder_dupes = 0
        all_files = [p for p in folder.rglob("*") if p.is_file()]
        print(f"  {len(all_files)} files found")

        for photo_path in sorted(all_files):
            if photo_path.suffix.lower() not in ACCEPTED_EXTS:
                continue

            photo_id = _sha256_id(photo_path)

            if photo_id in seen:
                skipped_dupe += 1
                folder_dupes += 1
                continue
            seen.add(photo_id)

            sidecar_data: dict | None = None
            sidecar_path = _find_sidecar(photo_path)
            if sidecar_path:
                try:
                    sidecar_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            else:
                no_sidecar += 1

            year = (
                (_year_from_sidecar(sidecar_data) if sidecar_data else None)
                or _year_from_folder(photo_path.parent.name)
                or "unknown"
            )

            dest_key = f"photos/{year}/{photo_path.name}"

            # Resolve the local path for this key so we can detect filename collisions.
            dest_local = settings.data_dir / dest_key
            if not dry_run and dest_local.exists():
                dest_key = f"photos/{year}/{photo_id}_{photo_path.name}"
                dest_local = settings.data_dir / dest_key

            if dry_run:
                print(f"  [dry] {photo_path.name} → {dest_key}")
            else:
                photo_bytes = photo_path.read_bytes()
                storage.write_bytes(dest_key, photo_bytes)
                if sidecar_data:
                    sidecar_key = f"sidecars/{photo_id}.json"
                    storage.write_bytes(
                        sidecar_key,
                        json.dumps(sidecar_data, ensure_ascii=False, indent=2).encode(),
                        "application/json",
                    )
                items.append((photo_id, dest_local))

            merged += 1
            folder_count += 1

        print(f"  {folder_count} merged, {folder_dupes} skipped (already indexed)")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}merge done:")
    print(f"  {merged} merged")
    print(f"  {skipped_dupe} duplicates skipped")
    print(f"  {no_sidecar} files had no sidecar JSON")

    return {
        "merged": merged,
        "skipped_dupe": skipped_dupe,
        "no_sidecar": no_sidecar,
        "items": items,
    }
