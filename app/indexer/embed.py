import json
from datetime import datetime, timezone

from ..chroma import assert_embed_model, get_collection
from ..config import get_settings
from ..db import get_conn
from .providers import get_embed_provider


def run_embed(reindex: bool = False) -> int:
    conn = get_conn()
    settings = get_settings()
    provider = get_embed_provider()

    assert_embed_model(settings.embed_model)

    if reindex:
        rows = conn.execute(
            "SELECT id, caption, tags, taken_at FROM photos WHERE caption IS NOT NULL"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, caption, tags, taken_at FROM photos "
            "WHERE caption IS NOT NULL AND vector_indexed_at IS NULL"
        ).fetchall()

    collection = get_collection()
    embedded = 0
    skipped = 0

    for row in rows:
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
            print(f"  embed error {row['id']}: {e}")
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
        embedded += 1

    conn.commit()
    conn.close()
    print(f"embed: {embedded} embedded, {skipped} skipped")
    return embedded
