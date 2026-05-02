import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import exifread
import pillow_heif
from PIL import Image

from ..config import get_settings
from ..db import get_conn, init_schema

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
    conn = get_conn()
    init_schema(conn)

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

    for photo_id, path in items:
        existing = conn.execute(
            "SELECT scan_indexed_at FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()

        if existing and existing["scan_indexed_at"] and not reindex:
            skipped += 1
            continue

        # Check path collision for different id
        path_existing = conn.execute(
            "SELECT id FROM photos WHERE storage_path = ?", (str(path),)
        ).fetchone()
        if path_existing and path_existing["id"] != photo_id:
            # Same path, different content — update the row
            conn.execute("DELETE FROM photos WHERE storage_path = ?", (str(path),))

        exif = _extract_exif(path)
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            INSERT INTO photos (id, storage_path, original_filename, taken_at, lat, lng, scan_indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                storage_path = excluded.storage_path,
                taken_at = excluded.taken_at,
                lat = excluded.lat,
                lng = excluded.lng,
                scan_indexed_at = excluded.scan_indexed_at
            """,
            (
                photo_id,
                str(path),
                path.name,
                exif["taken_at"].isoformat() if exif["taken_at"] else None,
                exif["lat"],
                exif["lng"],
                now,
            ),
        )
        scanned += 1

    conn.commit()
    conn.close()
    print(f"scan: {scanned} indexed, {skipped} skipped")
    return scanned


def _walk_photos(root: Path):
    for p in root.rglob("*"):
        if p.suffix.lower() in ACCEPTED_EXTS and p.is_file():
            yield p
