import json
import time
from datetime import datetime, timezone

from ..chroma import assert_embed_model, get_collection
from ..config import get_settings
from ..db import get_conn
from .providers import get_embed_provider


def run_embed(reindex: bool = False, limit: int | None = None) -> int:
    conn = get_conn()
    settings = get_settings()
    provider = get_embed_provider()

    print(f"embed: model={settings.embed_model} reindex={reindex} limit={limit}")
    assert_embed_model(settings.embed_model)

    query = (
        "SELECT id, caption, tags, taken_at FROM photos WHERE caption IS NOT NULL"
        if reindex
        else "SELECT id, caption, tags, taken_at FROM photos "
             "WHERE caption IS NOT NULL AND vector_indexed_at IS NULL"
    )
    if limit:
        query += f" LIMIT {limit}"

    rows = conn.execute(query).fetchall()
    total = len(rows)
    print(f"embed: {total} photos to embed")

    if total == 0:
        conn.close()
        print("embed: nothing to do")
        return 0

    collection = get_collection()
    embedded = 0
    skipped = 0
    t0 = time.time()

    for i, row in enumerate(rows, 1):
        tags: list[str] = []
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except (json.JSONDecodeError, TypeError):
                tags = []

        text = row["caption"]
        if tags:
            text = text + " " + " ".join(tags)

        try:
            vec = provider.embed(text)
        except Exception as e:
            print(f"  [{i}/{total}] SKIP {row['id']}: {e}")
            skipped += 1
            continue

        year = 0
        if row["taken_at"]:
            try:
                year = int(str(row["taken_at"])[:4])
            except (ValueError, TypeError):
                year = 0

        collection.upsert(
            ids=[row["id"]],
            embeddings=[vec],
            metadatas=[{"year": year}],
        )

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE photos SET vector_indexed_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        conn.commit()  # release lock immediately — allows caption to interleave
        embedded += 1

        if i % 10 == 0 or i == total:
            elapsed = time.time() - t0
            rate = embedded / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            print(
                f"  [{i}/{total}] {embedded} embedded, {skipped} skipped"
                f" | {rate:.1f}/s | ETA {eta:.0f}s"
            )

    conn.close()

    elapsed = time.time() - t0
    print(
        f"embed: done — {embedded} embedded, {skipped} skipped"
        f" in {elapsed:.1f}s ({embedded/elapsed:.1f}/s)"
    )
    return embedded
