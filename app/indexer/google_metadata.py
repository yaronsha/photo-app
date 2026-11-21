"""
Indexer step: enrich photos from Google Takeout sidecar JSON files.

Reads data/sidecars/{photo_id}.json and populates:
  - taken_at        (photoTakenTime — fills a missing EXIF date, and overrides
                     EXIF when the two disagree by more than a day; see
                     _resolve_taken_at)
  - lat / lng       (geoData — supplements EXIF)
  - description     (user-written note from Google Photos)
  - google_people   (raw JSON of Google face tags)
  - photo_people    (mapped to person IDs via config google_name_aliases)
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from ..config import get_settings
from ..db import Photo, get_session, init_schema
from ..db.upsert import upsert_person, upsert_photo_person
from ..storage import get_storage
from ..storage.base import KeyNotFound


def _ts_to_iso(timestamp_str: str) -> str | None:
    try:
        return datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc).isoformat()
    except Exception:
        return None


# EXIF dates are camera-local time (stored as if UTC); photoTakenTime is true
# UTC. Gaps up to this size are just timezone offsets (max is UTC+14), so
# anything larger means the two sources really disagree.
_DATE_DISAGREEMENT = timedelta(days=1)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _resolve_taken_at(current: str | None, sidecar_ts: str | None) -> str | None:
    """Pick taken_at from the existing (EXIF) value and the sidecar timestamp.

    Scanners write the scan time into EXIF, and Google Photos keeps the
    user-corrected date in photoTakenTime, so a large disagreement means the
    sidecar is right. A small one is only a timezone offset, and EXIF (local
    time) is kept.
    """
    sidecar_iso = _ts_to_iso(sidecar_ts) if sidecar_ts else None
    if not sidecar_iso:
        return current
    current_dt = _parse_iso(current)
    if current_dt is None:
        return sidecar_iso
    sidecar_dt = datetime.fromisoformat(sidecar_iso)
    if abs(current_dt - sidecar_dt) > _DATE_DISAGREEMENT:
        return sidecar_iso
    return current


def run_google_metadata(reindex: bool = False) -> int:
    settings = get_settings()
    storage = get_storage()
    init_schema()

    aliases: dict[str, str] = {
        k.lower(): v
        for k, v in getattr(settings, "google_name_aliases", {}).items()
    }

    with get_session() as session:
        # Seed people table from config (idempotent)
        for person in settings.people:
            upsert_person(
                session, id=person.id, name=person.name, family_id=person.family_id
            )

        stmt = select(Photo.id, Photo.taken_at, Photo.lat, Photo.lng)
        if not reindex:
            stmt = stmt.where(Photo.google_metadata_indexed_at.is_(None))
        rows = session.execute(stmt).all()

        enriched = skipped = no_sidecar = 0
        now = datetime.now(timezone.utc).isoformat()

        for photo_id, taken_at, lat, lng in rows:
            sidecar_key = f"sidecars/{photo_id}.json"

            if not storage.exists(sidecar_key):
                no_sidecar += 1
                session.execute(
                    update(Photo)
                    .where(Photo.id == photo_id)
                    .values(google_metadata_indexed_at=now)
                )
                continue

            try:
                data = json.loads(storage.read_bytes(sidecar_key).decode("utf-8"))
            except KeyNotFound:
                # exists() said yes; gone now — treat as no_sidecar.
                no_sidecar += 1
                session.execute(
                    update(Photo)
                    .where(Photo.id == photo_id)
                    .values(google_metadata_indexed_at=now)
                )
                continue
            except json.JSONDecodeError as exc:
                print(f"  google_metadata bad json {photo_id}: {exc}")
                skipped += 1
                continue
            except Exception as exc:
                print(
                    f"  google_metadata TRANSIENT read error {photo_id}: "
                    f"{type(exc).__name__}: {exc}"
                )
                skipped += 1
                continue

            # taken_at: sidecar fills a missing EXIF date, and overrides EXIF
            # when they disagree by more than a timezone offset (scans).
            ts = (data.get("photoTakenTime") or {}).get("timestamp")
            new_taken_at = _resolve_taken_at(taken_at, ts)

            # lat/lng: sidecar supplements EXIF
            new_lat = lat
            new_lng = lng
            geo = data.get("geoData", {})
            if geo.get("latitude") and not new_lat:
                new_lat = geo["latitude"]
            if geo.get("longitude") and not new_lng:
                new_lng = geo["longitude"]

            description = data.get("description") or None
            google_people_raw = data.get("people")

            session.execute(
                update(Photo)
                .where(Photo.id == photo_id)
                .values(
                    taken_at=new_taken_at,
                    lat=new_lat,
                    lng=new_lng,
                    description=description,
                    google_people=google_people_raw if google_people_raw else None,
                    google_metadata_indexed_at=now,
                )
            )

            # Populate photo_people from Google face tags
            if google_people_raw and aliases:
                for entry in google_people_raw:
                    raw_name = (entry.get("name") or "").strip().lower()
                    person_id = aliases.get(raw_name)
                    if not person_id:
                        continue
                    upsert_photo_person(
                        session, photo_id=photo_id, person_id=person_id
                    )

            enriched += 1

    print(f"google_metadata: {enriched} enriched, {no_sidecar} no sidecar, {skipped} errors")
    return enriched
