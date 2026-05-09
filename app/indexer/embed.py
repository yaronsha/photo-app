import time
from datetime import datetime, timezone

from sqlalchemy import or_, select, update

from ..chroma import assert_embed_model, get_collection
from ..config import get_settings
from ..db import Photo, get_session
from .providers import get_embed_provider


def run_embed(reindex: bool = False, limit: int | None = None) -> int:
    settings = get_settings()
    provider = get_embed_provider()

    print(f"embed: model={settings.embed_model} reindex={reindex} limit={limit}")
    assert_embed_model(settings.embed_model)

    with get_session() as session:
        stmt = select(
            Photo.id,
            Photo.caption,
            Photo.activities,
            Photo.content_type,
            Photo.taken_at,
            Photo.caption_schema_version,
        ).where(
            Photo.caption.is_not(None),
            or_(Photo.content_type.is_(None), Photo.content_type.notin_(["document", "other"])),
        )
        if not reindex:
            stmt = stmt.where(
                or_(
                    Photo.embed_schema_version.is_(None),
                    Photo.embed_schema_version < Photo.caption_schema_version,
                )
            )
        if limit:
            stmt = stmt.limit(limit)

        rows = session.execute(stmt).all()
        total = len(rows)
        print(f"embed: {total} photos to embed")

        if total == 0:
            print("embed: nothing to do")
            return 0

        collection = get_collection()
        embedded = 0
        skipped = 0
        t0 = time.time()

        for i, row in enumerate(rows, 1):
            activities: list[str] = row.activities or []

            text = row.caption
            if activities:
                text = text + " " + " ".join(activities)

            try:
                vec = provider.embed(text)
            except Exception as e:
                print(f"  [{i}/{total}] SKIP {row.id}: {e}")
                skipped += 1
                continue

            year = 0
            if row.taken_at:
                try:
                    year = int(str(row.taken_at)[:4])
                except (ValueError, TypeError):
                    year = 0

            collection.upsert(
                ids=[row.id],
                embeddings=[vec],
                metadatas=[{"year": year}],
            )

            now = datetime.now(timezone.utc).isoformat()
            session.execute(
                update(Photo)
                .where(Photo.id == row.id)
                .values(
                    vector_indexed_at=now,
                    embed_schema_version=row.caption_schema_version,
                )
            )
            session.commit()  # release lock immediately — caption can interleave
            embedded += 1

            if i % 10 == 0 or i == total:
                elapsed = time.time() - t0
                rate = embedded / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate if rate > 0 else 0
                print(
                    f"  [{i}/{total}] {embedded} embedded, {skipped} skipped"
                    f" | {rate:.1f}/s | ETA {eta:.0f}s"
                )

    elapsed = time.time() - t0
    print(
        f"embed: done — {embedded} embedded, {skipped} skipped"
        f" in {elapsed:.1f}s ({embedded/elapsed:.1f}/s)"
    )
    return embedded
