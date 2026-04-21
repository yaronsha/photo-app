"""
Indexer step: enrich photos from Google Takeout sidecar JSON files.

Reads data/sidecars/{photo_id}.json and populates:
  - taken_at        (photoTakenTime — authoritative for old/scanned photos)
  - lat / lng       (geoData — supplements EXIF)
  - description     (user-written note from Google Photos)
  - google_people   (raw JSON of Google face tags)
  - photo_people    (mapped to person IDs via config google_name_aliases)
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..db import get_conn, init_schema


def _ts_to_iso(timestamp_str: str) -> str | None:
    try:
        return datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc).isoformat()
    except Exception:
        return None


def run_google_metadata(reindex: bool = False) -> int:
    settings = get_settings()
    conn = get_conn()
    init_schema(conn)

    sidecars_dir = settings.data_dir / "sidecars"
    if not sidecars_dir.exists():
        print("google_metadata: no sidecars dir found — run merge_takeouts.py first")
        return 0

    aliases: dict[str, str] = {
        k.lower(): v
        for k, v in getattr(settings, "google_name_aliases", {}).items()
    }

    rows = conn.execute(
        "SELECT id, taken_at, lat, lng FROM photos"
        + ("" if reindex else " WHERE google_metadata_indexed_at IS NULL")
    ).fetchall()

    enriched = skipped = no_sidecar = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        photo_id = row["id"]
        sidecar_path = sidecars_dir / f"{photo_id}.json"

        if not sidecar_path.exists():
            no_sidecar += 1
            conn.execute(
                "UPDATE photos SET google_metadata_indexed_at = ? WHERE id = ?",
                (now, photo_id),
            )
            continue

        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception:
            skipped += 1
            continue

        # taken_at: sidecar wins when EXIF is absent
        taken_at = row["taken_at"]
        ts = data.get("photoTakenTime", {}).get("timestamp")
        if ts and not taken_at:
            taken_at = _ts_to_iso(ts)

        # lat/lng: sidecar supplements EXIF
        lat = row["lat"]
        lng = row["lng"]
        geo = data.get("geoData", {})
        if geo.get("latitude") and not lat:
            lat = geo["latitude"]
        if geo.get("longitude") and not lng:
            lng = geo["longitude"]

        description = data.get("description") or None
        google_people_raw = data.get("people")
        google_people_json = json.dumps(google_people_raw, ensure_ascii=False) if google_people_raw else None

        conn.execute(
            """
            UPDATE photos SET
                taken_at = ?,
                lat = ?,
                lng = ?,
                description = ?,
                google_people = ?,
                google_metadata_indexed_at = ?
            WHERE id = ?
            """,
            (taken_at, lat, lng, description, google_people_json, now, photo_id),
        )

        # Populate photo_people from Google face tags
        if google_people_raw and aliases:
            for entry in google_people_raw:
                raw_name = (entry.get("name") or "").strip().lower()
                person_id = aliases.get(raw_name)
                if not person_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO photo_people (photo_id, person_id, face_bbox, confidence)
                    VALUES (?, ?, NULL, NULL)
                    ON CONFLICT(photo_id, person_id) DO NOTHING
                    """,
                    (photo_id, person_id),
                )

        enriched += 1

    conn.commit()
    conn.close()
    print(f"google_metadata: {enriched} enriched, {no_sidecar} no sidecar, {skipped} errors")
    return enriched
