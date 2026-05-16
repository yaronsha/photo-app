#!/usr/bin/env python3
"""Transfer embeddings from local ChromaDB to Postgres pgvector.

Usage:
    uv run python scripts/transfer_embeddings.py [--chroma PATH] [--pg URL] [--batch N]

Reads vectors + metadata from the local Chroma `photos` collection and
upserts them into the Postgres `embeddings` table (pgvector). Idempotent:
re-running overrides existing rows by photo_id.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

load_dotenv()

from app.config import get_settings
from app.db.orm import Embedding


def _pg_url() -> str:
    url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL") or ""
    if not url:
        raise SystemExit("Error: set DATABASE_URL_DIRECT or DATABASE_URL in env/.env")
    return url


def _chroma_path(arg: str | None) -> str:
    if arg:
        return arg
    return str(get_settings().chroma_path)


def transfer(chroma_path: str, pg_url: str, batch_size: int) -> None:
    import chromadb

    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(
        name="photos", metadata={"hnsw:space": "cosine"}
    )

    total = collection.count()
    print(f"Chroma collection 'photos': {total} vectors")
    if total == 0:
        print("Nothing to transfer.")
        return

    default_model = (collection.metadata or {}).get("embed_model") or "unknown"
    print(f"Default embed_model: {default_model}")

    engine = create_engine(pg_url)
    Session = sessionmaker(bind=engine)

    offset = 0
    transferred = 0
    while offset < total:
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["embeddings", "metadatas"],
        )
        ids = batch.get("ids")
        embs = batch.get("embeddings")
        metas = batch.get("metadatas")
        ids = list(ids) if ids is not None else []
        embs = list(embs) if embs is not None else []
        metas = list(metas) if metas is not None else []
        if not ids:
            break

        rows = []
        for i, pid in enumerate(ids):
            meta = metas[i] if i < len(metas) and metas[i] else {}
            year = meta.get("year")
            year = int(year) if year not in (None, 0) else None
            model = meta.get("embed_model") or default_model
            rows.append(
                {
                    "photo_id": pid,
                    "embedding": list(embs[i]),
                    "embed_model": model,
                    "year": year,
                }
            )

        stmt = pg_insert(Embedding).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["photo_id"],
            set_={
                "embedding": stmt.excluded.embedding,
                "embed_model": stmt.excluded.embed_model,
                "year": stmt.excluded.year,
            },
        )
        with Session() as session:
            session.execute(stmt)
            session.commit()

        transferred += len(rows)
        offset += batch_size
        print(f"  {transferred}/{total}", end="\r", flush=True)

    print(f"  {transferred}/{total} done.    ")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--chroma", help="Chroma directory (default: data/chroma)")
    parser.add_argument("--pg", help="Postgres URL (default: DATABASE_URL_DIRECT or DATABASE_URL env)")
    parser.add_argument("--batch", type=int, default=500, help="Vectors per batch (default: 500)")
    args = parser.parse_args()

    chroma_path = _chroma_path(args.chroma)
    pg_url = args.pg or _pg_url()

    print(f"Chroma:   {chroma_path}")
    print(f"Postgres: {pg_url.split('@')[-1]}")
    print()

    transfer(chroma_path, pg_url, args.batch)
    print("\nTransfer complete.")


if __name__ == "__main__":
    main()
