import json
from datetime import datetime, timezone
from pathlib import Path

from ..db import get_conn
from .providers import get_caption_provider

DEFAULT_LIMIT = 50


def run_caption(limit: int = DEFAULT_LIMIT, reindex: bool = False) -> int:
    conn = get_conn()
    provider = get_caption_provider()

    if reindex:
        rows = conn.execute(
            "SELECT id, storage_path FROM photos WHERE scan_indexed_at IS NOT NULL LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, storage_path FROM photos "
            "WHERE scan_indexed_at IS NOT NULL AND caption_indexed_at IS NULL "
            "LIMIT ?",
            (limit,),
        ).fetchall()

    captioned = 0
    skipped = 0

    for row in rows:
        path = Path(row["storage_path"])
        if not path.exists():
            print(f"  missing file: {path} — skip")
            skipped += 1
            continue

        try:
            result = provider.caption(path)
        except Exception as e:
            print(f"  caption error {path.name}: {e}")
            skipped += 1
            continue

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE photos SET caption = ?, tags = ?, caption_indexed_at = ? WHERE id = ?",
            (
                result["caption"],
                json.dumps(result["tags"]),
                now,
                row["id"],
            ),
        )
        captioned += 1

    conn.commit()
    conn.close()
    print(f"caption: {captioned} captioned, {skipped} skipped")
    return captioned
