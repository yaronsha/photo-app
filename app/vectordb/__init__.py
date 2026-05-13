"""Vector backend factory.

Select backend via VECTOR_BACKEND env var:
  chroma    — local ChromaDB (default, rollback path)
  pgvector  — Supabase Postgres + pgvector
"""
from __future__ import annotations

import os

from .base import VectorBackend


def get_vector_backend() -> VectorBackend:
    backend = os.getenv("VECTOR_BACKEND", "chroma")

    if backend == "chroma":
        from ..config import get_settings
        from .chroma_backend import ChromaBackend

        settings = get_settings()
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        return ChromaBackend(str(settings.chroma_path))

    if backend == "pgvector":
        from ..db.session import SessionLocal
        from .pgvector_backend import PgvectorBackend

        return PgvectorBackend(SessionLocal)

    raise ValueError(f"Unknown VECTOR_BACKEND={backend!r}. Use 'chroma' or 'pgvector'.")
