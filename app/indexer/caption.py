import asyncio
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select, update

from ..db import Photo, get_session
from .providers import get_caption_provider

DEFAULT_LIMIT = 50
CONCURRENCY = 5
CAPTION_SCHEMA_VERSION = 4


def run_caption(limit: int = DEFAULT_LIMIT, reindex: bool = False) -> int:
    return asyncio.run(_run_caption_async(limit=limit, reindex=reindex))


async def _run_caption_async(limit: int, reindex: bool) -> int:
    provider = get_caption_provider()

    with get_session() as session:
        stmt = select(
            Photo.id, Photo.storage_path, Photo.lat, Photo.lng, Photo.location_name
        ).where(Photo.scan_indexed_at.is_not(None))
        if not reindex:
            stmt = stmt.where(
                or_(
                    Photo.caption_indexed_at.is_(None),
                    Photo.caption_schema_version.is_(None),
                    Photo.caption_schema_version < CAPTION_SCHEMA_VERSION,
                )
            )
        stmt = stmt.limit(limit)
        rows = session.execute(stmt).all()

    print(f"caption: processing {len(rows)} photos (concurrency={CONCURRENCY})")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    captioned = 0
    skipped = 0

    async def process(row):
        nonlocal captioned, skipped
        path = Path(row.storage_path)
        if not path.exists():
            print(f"  missing file: {path} — skip")
            skipped += 1
            return

        location_hint = row.location_name or (
            f"{row.lat:.4f},{row.lng:.4f}" if row.lat and row.lng else None
        )

        async with semaphore:
            try:
                result = await provider.caption(path, location_hint=location_hint)
            except Exception as e:
                print(f"  error {path.name}: {e}")
                skipped += 1
                return

        now = datetime.now(timezone.utc).isoformat()
        # Per-task session: each writer has its own short transaction.
        # Concurrent writers serialize via SQLite's busy timeout (engine timeout=30).
        with get_session() as task_session:
            task_session.execute(
                update(Photo)
                .where(Photo.id == row.id)
                .values(
                    caption=result["caption"],
                    tags=result["tags"],
                    activities=result["activities"],
                    content_type=result["content_type"],
                    subject_type=result["subject_type"],
                    primary_focus=result["primary_focus"],
                    indoor_outdoor=result["indoor_outdoor"],
                    setting_type=result["setting_type"],
                    sharpness=result["sharpness"],
                    face_clarity_score=result["face_clarity_score"],
                    caption_indexed_at=now,
                    caption_schema_version=CAPTION_SCHEMA_VERSION,
                )
            )
        captioned += 1

    await asyncio.gather(*[process(row) for row in rows])

    print(f"caption: {captioned} captioned, {skipped} skipped")
    return captioned
