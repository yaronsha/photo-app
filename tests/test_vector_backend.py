"""Contract tests for VectorBackend implementations.

TestChromaBackend  — no marker, no Docker, runs in unit CI job.
TestPgvectorBackend — @requires_postgres, runs in integration CI job.

Both classes assert identical behaviour:
  upsert / count / query / year_filter / distinct_embed_models.
"""
import pytest

# Orthogonal unit vectors — unambiguous cosine ranking.
# VEC_A · VEC_QUERY = 1  (distance 0, closest)
# VEC_B · VEC_QUERY = 0  (distance 1, further)
VEC_A = [1.0] + [0.0] * 1535
VEC_B = [0.0, 1.0] + [0.0] * 1534
VEC_QUERY = [1.0] + [0.0] * 1535


# ── helpers ──────────────────────────────────────────────────────────────────

def _seed_pg_photo(session_factory, photo_id: str) -> None:
    """Insert a minimal Photo row so Embedding FK constraint is satisfied."""
    from app.db.orm import Photo
    with session_factory() as s:
        s.merge(Photo(
            id=photo_id,
            storage_path=f"/tmp/{photo_id}.jpg",
            original_filename=f"{photo_id}.jpg",
        ))
        s.commit()


# ── ChromaBackend (unit job, no Docker) ──────────────────────────────────────

class TestChromaBackend:
    @pytest.fixture()
    def backend(self, tmp_path):
        from app.vectordb.chroma_backend import ChromaBackend
        return ChromaBackend(str(tmp_path / "chroma"))

    def test_count_empty(self, backend):
        assert backend.count() == 0

    def test_upsert_increments_count(self, backend):
        backend.upsert("p1", VEC_A, "model-x", 2020)
        assert backend.count() == 1

    def test_upsert_idempotent(self, backend):
        backend.upsert("p1", VEC_A, "model-x", 2020)
        backend.upsert("p1", VEC_B, "model-x", 2021)
        assert backend.count() == 1

    def test_query_returns_nearest_first(self, backend):
        backend.upsert("p_a", VEC_A, "model-x", 2020)
        backend.upsert("p_b", VEC_B, "model-x", 2020)
        results = backend.query(VEC_QUERY, n=2)
        assert [r[0] for r in results] == ["p_a", "p_b"]

    def test_query_distances_are_nonnegative(self, backend):
        backend.upsert("p1", VEC_A, "model-x", 2020)
        backend.upsert("p2", VEC_B, "model-x", 2020)
        for _, dist in backend.query(VEC_QUERY, n=2):
            assert dist >= 0

    def test_year_filter_restricts_results(self, backend):
        backend.upsert("p2020", VEC_A, "model-x", 2020)
        backend.upsert("p2021", VEC_B, "model-x", 2021)
        results = backend.query(VEC_QUERY, n=2, year_filter=2020)
        ids = [r[0] for r in results]
        assert "p2020" in ids
        assert "p2021" not in ids

    def test_distinct_embed_models(self, backend):
        backend.upsert("p1", VEC_A, "model-x", 2020)
        models = backend.distinct_embed_models()
        assert isinstance(models, set)


# ── PgvectorBackend (integration job, needs Postgres) ────────────────────────

@pytest.mark.requires_postgres
class TestPgvectorBackend:
    def test_count_empty(self, pg_backend):
        assert pg_backend.count() == 0

    def test_upsert_increments_count(self, pg_backend, pg_session_factory):
        _seed_pg_photo(pg_session_factory, "p1")
        pg_backend.upsert("p1", VEC_A, "model-x", 2020)
        assert pg_backend.count() == 1

    def test_upsert_idempotent(self, pg_backend, pg_session_factory):
        _seed_pg_photo(pg_session_factory, "p1")
        pg_backend.upsert("p1", VEC_A, "model-x", 2020)
        pg_backend.upsert("p1", VEC_B, "model-x", 2021)
        assert pg_backend.count() == 1

    def test_query_returns_nearest_first(self, pg_backend, pg_session_factory):
        _seed_pg_photo(pg_session_factory, "p_a")
        _seed_pg_photo(pg_session_factory, "p_b")
        pg_backend.upsert("p_a", VEC_A, "model-x", 2020)
        pg_backend.upsert("p_b", VEC_B, "model-x", 2020)
        results = pg_backend.query(VEC_QUERY, n=2)
        assert results[0][0] == "p_a"

    def test_query_distances_are_nonnegative(self, pg_backend, pg_session_factory):
        _seed_pg_photo(pg_session_factory, "p1")
        _seed_pg_photo(pg_session_factory, "p2")
        pg_backend.upsert("p1", VEC_A, "model-x", 2020)
        pg_backend.upsert("p2", VEC_B, "model-x", 2020)
        for _, dist in pg_backend.query(VEC_QUERY, n=2):
            assert dist >= 0

    def test_year_filter_restricts_results(self, pg_backend, pg_session_factory):
        _seed_pg_photo(pg_session_factory, "p2020")
        _seed_pg_photo(pg_session_factory, "p2021")
        pg_backend.upsert("p2020", VEC_A, "model-x", 2020)
        pg_backend.upsert("p2021", VEC_B, "model-x", 2021)
        results = pg_backend.query(VEC_QUERY, n=2, year_filter=2020)
        ids = [r[0] for r in results]
        assert "p2020" in ids
        assert "p2021" not in ids

    def test_distinct_embed_models(self, pg_backend, pg_session_factory):
        _seed_pg_photo(pg_session_factory, "p1")
        pg_backend.upsert("p1", VEC_A, "model-x", 2020)
        assert pg_backend.distinct_embed_models() == {"model-x"}
