"""Search integration tests using real vector backends (no mocked query path).

Unit job: ChromaBackend (ephemeral tmp_path, no Docker).
  Tests the full chain: embed(mocked) → chroma.query → SQLite join → results.

Integration job (@requires_postgres): PgvectorBackend.
  Same chain but with real Postgres vector query.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.db import Photo, get_session, init_schema
from app.search.query import search
from app.vectordb.chroma_backend import ChromaBackend

from .conftest import FAKE_EMBED_VEC, make_png

PHOTO_ID = "integ_photo_001"
TAKEN_AT = "2022-07-15T12:00:00+00:00"


def _seed_sqlite_photo(photos_dir, photo_id: str = PHOTO_ID) -> None:
    photo_path = photos_dir / "beach.jpg"
    make_png(photo_path)
    init_schema()
    with get_session() as s:
        s.add(Photo(
            id=photo_id,
            storage_path=str(photo_path),
            original_filename="beach.jpg",
            caption="sunny beach day",
            taken_at=TAKEN_AT,
            scan_indexed_at=TAKEN_AT,
            caption_indexed_at=TAKEN_AT,
            vector_indexed_at=TAKEN_AT,
            content_type="photo",
        ))


def _mock_embed_provider(vec=FAKE_EMBED_VEC):
    provider = MagicMock()
    provider.embed.return_value = vec
    return provider


# ── ChromaBackend (unit job, no Docker) ──────────────────────────────────────

def test_search_full_chain_chroma(tmp_env, tmp_path):
    """vector embed (mocked) → ChromaBackend.query → SQLite join → result."""
    _seed_sqlite_photo(tmp_env["photos_dir"])

    backend = ChromaBackend(str(tmp_path / "chroma"))
    backend.upsert(PHOTO_ID, FAKE_EMBED_VEC, "text-embedding-3-small", 2022)

    with patch("app.search.query.get_embed_provider", return_value=_mock_embed_provider()):
        results, has_more = search("beach", vector_db=backend)

    assert len(results) == 1
    assert results[0].id == PHOTO_ID
    assert results[0].caption == "sunny beach day"
    assert not has_more


def test_search_date_filter_chroma(tmp_env, tmp_path):
    """Date filter applied after vector query — only matching photo returned."""
    _seed_sqlite_photo(tmp_env["photos_dir"], PHOTO_ID)
    backend = ChromaBackend(str(tmp_path / "chroma"))
    backend.upsert(PHOTO_ID, FAKE_EMBED_VEC, "text-embedding-3-small", 2022)

    with patch("app.search.query.get_embed_provider", return_value=_mock_embed_provider()):
        results, _ = search(
            "beach", vector_db=backend, date_from="2022-07-01", date_to="2022-07-31"
        )
    assert len(results) == 1

    with patch("app.search.query.get_embed_provider", return_value=_mock_embed_provider()):
        results, _ = search(
            "beach", vector_db=backend, date_from="2021-01-01", date_to="2021-12-31"
        )
    assert len(results) == 0


def test_search_no_vector_match_chroma(tmp_env, tmp_path):
    """Empty vector backend → search returns no results even with SQLite row."""
    _seed_sqlite_photo(tmp_env["photos_dir"])
    backend = ChromaBackend(str(tmp_path / "chroma"))
    # intentionally not upserting → count() == 0

    with patch("app.search.query.get_embed_provider", return_value=_mock_embed_provider()):
        results, _ = search("beach", vector_db=backend)

    assert results == []


# ── PgvectorBackend (integration job, needs Postgres) ────────────────────────

def _seed_pg_photo_for_search(session_factory, photo_id: str) -> None:
    """Insert minimal Photo row in Postgres for FK compliance."""
    from app.db.orm import Photo as PgPhoto
    with session_factory() as s:
        s.merge(PgPhoto(
            id=photo_id,
            storage_path=f"/tmp/{photo_id}.jpg",
            original_filename=f"{photo_id}.jpg",
        ))
        s.commit()


@pytest.mark.requires_postgres
def test_search_full_chain_pgvector(tmp_env, pg_session_factory, pg_backend):
    """vector embed (mocked) → PgvectorBackend.query → SQLite join → result."""
    _seed_sqlite_photo(tmp_env["photos_dir"])
    _seed_pg_photo_for_search(pg_session_factory, PHOTO_ID)
    pg_backend.upsert(PHOTO_ID, FAKE_EMBED_VEC, "text-embedding-3-small", 2022)

    with patch("app.search.query.get_embed_provider", return_value=_mock_embed_provider()):
        results, has_more = search("beach", vector_db=pg_backend)

    assert len(results) == 1
    assert results[0].id == PHOTO_ID
    assert results[0].caption == "sunny beach day"
    assert not has_more


@pytest.mark.requires_postgres
def test_search_date_filter_pgvector(tmp_env, pg_session_factory, pg_backend):
    """Date filter applied after pgvector query — only matching photo returned."""
    _seed_sqlite_photo(tmp_env["photos_dir"], PHOTO_ID)
    _seed_pg_photo_for_search(pg_session_factory, PHOTO_ID)
    pg_backend.upsert(PHOTO_ID, FAKE_EMBED_VEC, "text-embedding-3-small", 2022)

    with patch("app.search.query.get_embed_provider", return_value=_mock_embed_provider()):
        in_range, _ = search(
            "beach", vector_db=pg_backend, date_from="2022-07-01", date_to="2022-07-31"
        )
    assert len(in_range) == 1

    with patch("app.search.query.get_embed_provider", return_value=_mock_embed_provider()):
        out_of_range, _ = search(
            "beach", vector_db=pg_backend, date_from="2021-01-01", date_to="2021-12-31"
        )
    assert len(out_of_range) == 0
