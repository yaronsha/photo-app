import hashlib
from datetime import datetime, timezone
from pathlib import Path

import exifread
import pillow_heif
from sqlalchemy import delete, select

from ..config import get_settings
from ..db import Photo, get_session, init_schema
from ..db.upsert import upsert_photo_scan

pillow_heif.register_heif_opener()

ACCEPTED_EXTS = {".jpg", ".jpeg", ".png", ".heic"}


def _sha256_id(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _extract_exif(path: Path) -> dict:
    result: dict = {"taken_at": None, "lat": None, "lng": None}
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, stop_tag="GPS GPSLongitude", details=False)
        dt_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if dt_tag:
            try:
                result["taken_at"] = datetime.strptime(
                    str(dt_tag), "%Y:%m:%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        lat = _gps_decimal(
            tags.get("GPS GPSLatitude"), tags.get("GPS GPSLatitudeRef")
        )
        lng = _gps_decimal(
            tags.get("GPS GPSLongitude"), tags.get("GPS GPSLongitudeRef")
        )
        result["lat"] = lat
        result["lng"] = lng
    except Exception:
        pass
    return result


def _gps_decimal(coord_tag, ref_tag) -> float | None:
    if coord_tag is None:
        return None
    try:
        vals = coord_tag.values
        d = float(vals[0].num) / float(vals[0].den)
        m = float(vals[1].num) / float(vals[1].den)
        s = float(vals[2].num) / float(vals[2].den)
        dec = d + m / 60 + s / 3600
        if ref_tag and str(ref_tag) in ("S", "W"):
            dec = -dec
        return dec
    except Exception:
        return None


def run_scan(
    reindex: bool = False,
    prehashed: list[tuple[str, Path]] | None = None,
) -> int:
    settings = get_settings()
    init_schema()

    photos_dir = settings.photos_dir
    if not photos_dir.exists():
        print(f"photos_dir {photos_dir} does not exist — creating empty dir")
        photos_dir.mkdir(parents=True, exist_ok=True)

    scanned = 0
    skipped = 0

    if prehashed is not None:
        items = iter(prehashed)
    else:
        items = ((_sha256_id(p), p) for p in _walk_photos(photos_dir))

    with get_session() as session:
        for photo_id, path in items:
            existing = session.execute(
                select(Photo.scan_indexed_at).where(Photo.id == photo_id)
            ).first()

            if existing and existing[0] and not reindex:
                skipped += 1
                continue

            # Path collision: same path, different content — wipe old row first.
            path_existing = session.execute(
                select(Photo.id).where(Photo.storage_path == str(path))
            ).first()
            if path_existing and path_existing[0] != photo_id:
                session.execute(delete(Photo).where(Photo.storage_path == str(path)))

            exif = _extract_exif(path)
            now = datetime.now(timezone.utc).isoformat()

            upsert_photo_scan(
                session,
                id=photo_id,
                storage_path=str(path),
                original_filename=path.name,
                taken_at=exif["taken_at"].isoformat() if exif["taken_at"] else None,
                lat=exif["lat"],
                lng=exif["lng"],
                scan_indexed_at=now,
            )
            scanned += 1

    print(f"scan: {scanned} indexed, {skipped} skipped")
    return scanned


def _walk_photos(root: Path):
    for p in root.rglob("*"):
        if p.suffix.lower() in ACCEPTED_EXTS and p.is_file():
            yield p
