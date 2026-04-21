import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from ..db import get_conn
from .providers import get_caption_provider

DEFAULT_LIMIT = 50
CONCURRENCY = 6


def run_caption(limit: int = DEFAULT_LIMIT, reindex: bool = False) -> int:
    return asyncio.run(_run_caption_async(limit=limit, reindex=reindex))


async def _run_caption_async(limit: int, reindex: bool) -> int:
    conn = get_conn()
    provider = get_caption_provider()

    if reindex:
        rows = conn.execute(
            "SELECT id, storage_path, lat, lng, location_name FROM photos "
            "WHERE scan_indexed_at IS NOT NULL LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, storage_path, lat, lng, location_name FROM photos "
            "WHERE scan_indexed_at IS NOT NULL AND caption_indexed_at IS NULL "
            "LIMIT ?",
            (limit,),
        ).fetchall()

    print(f"caption: processing {len(rows)} photos (concurrency={CONCURRENCY})")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    captioned = 0
    skipped = 0

    async def process(row):
        nonlocal captioned, skipped
        path = Path(row["storage_path"])
        if not path.exists():
            print(f"  missing file: {path} — skip")
            skipped += 1
            return

        location_hint = row["location_name"] or (
            f"{row['lat']:.4f},{row['lng']:.4f}" if row["lat"] and row["lng"] else None
        )

        async with semaphore:
            try:
                result = await provider.caption(path, location_hint=location_hint)
            except Exception as e:
                print(f"  error {path.name}: {e}")
                skipped += 1
                return

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE photos SET caption = ?, tags = ?, caption_indexed_at = ? WHERE id = ?",
            (result["caption"], json.dumps(result["tags"]), now, row["id"]),
        )
        conn.commit()
        captioned += 1

    await asyncio.gather(*[process(row) for row in rows])

    conn.close()
    print(f"caption: {captioned} captioned, {skipped} skipped")
    return captioned
