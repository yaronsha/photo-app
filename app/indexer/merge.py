import hashlib
import json
import shutil
import sqlite3 as _sqlite
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings

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


def run_merge(folders: list[Path], dry_run: bool = False) -> dict:
    settings = get_settings()
    photos_dir = settings.photos_dir
    sidecars_dir = settings.data_dir / "sidecars"

    if not dry_run:
        photos_dir.mkdir(parents=True, exist_ok=True)
        sidecars_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    if settings.db_path.exists():
        con = _sqlite.connect(settings.db_path)
        seen.update(row[0] for row in con.execute("SELECT id FROM photos"))
        con.close()

    merged = skipped_dupe = no_sidecar = 0

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

            dest_dir = photos_dir / str(year)
            dest_name = photo_path.name
            dest_path = dest_dir / dest_name

            if dest_path.exists() and not dry_run:
                dest_name = f"{photo_id}_{photo_path.name}"
                dest_path = dest_dir / dest_name

            if dry_run:
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

        print(f"  {folder_count} merged, {folder_dupes} skipped (already indexed)")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}merge done:")
    print(f"  {merged} merged")
    print(f"  {skipped_dupe} duplicates skipped")
    print(f"  {no_sidecar} files had no sidecar JSON")

    return {"merged": merged, "skipped_dupe": skipped_dupe, "no_sidecar": no_sidecar}
