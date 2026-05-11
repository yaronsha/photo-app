# DB Migration: SQLite + ChromaDB → Supabase Postgres + pgvector

Phase 1. Replace metadata store and vector store with single Postgres instance.

## Why one DB instead of two

ChromaDB local-only. pgvector = vectors in same Postgres = single connection, transactional consistency, simpler ops. Embedding dim (1536, `text-embedding-3-small`) well within pgvector limits.

**Rollback escape hatch:** keep ChromaDB code path alive behind a `VECTOR_BACKEND` env var (`chroma` | `pgvector`). Local dev defaults to `chroma`. Cloud defaults to `pgvector`. If pgvector storage/RAM ever pinches on Supabase, can flip back to ChromaDB (laptop persistent disk) without code rewrite. Cost: maintain two impls behind one interface (cheap — same shape as storage abstraction in [storage.md](storage.md)).

## Supabase setup

1. Create project (region close to Vercel deployment region — e.g. both `us-east-1`)
2. SQL editor → `CREATE EXTENSION IF NOT EXISTS vector;`
3. Capture connection string: dashboard → Settings → Database → "Connection string" (URI mode, transaction pooler for serverless on port 6543; session/direct on 5432 for migrations)
4. Two URLs needed:
   - `DATABASE_URL` (app runtime, via PgBouncer pooler, port 6543)
   - `DATABASE_URL_DIRECT` (Alembic migrations, port 5432)

## Code changes

### 1. Drop `JSONString` TypeDecorator

Today (`app/db/types.py:10-34`): encodes list/dict as JSON-in-TEXT for SQLite.

Replace with `sqlalchemy.dialects.postgresql.JSONB` in columns. Keep `JSONString` only if SQLite local dev still required — wrap as dialect-conditional:

```python
# app/db/types.py
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JsonCol = JSON().with_variant(JSONB(), "postgresql")
```

Touch points: replace `JSONString` imports with `JsonCol`. Columns affected:
- `Photo.tags`, `Photo.activities`, `Photo.google_people` (in `app/db/orm.py` Photo model)
- `PhotoPerson.face_bbox` (in `app/db/orm.py` PhotoPerson model, line ~81)

### 2. SQLite-only pragmas — already guarded

`app/db/engine.py:63-79` — existing event listener sniffs `type(dbapi_connection).__module__` to detect SQLite. Already no-ops for Postgres connections. **No change needed.** Verify guard intact when other edits touch this file.

### 3. Engine creation

`app/db/engine.py:21-50` already honors `DATABASE_URL` env. Add psycopg dep:

```toml
# pyproject.toml
dependencies = [
  ...,
  "psycopg[binary]>=3.2",
  "pgvector>=0.3",
]
```

URL format: `postgresql+psycopg://user:pass@host:6543/postgres?sslmode=require&prepare_threshold=0`.

`prepare_threshold=0` is mandatory under Supabase pooler (transaction mode = no prepared statements). Omit it and you hit `prepared statement "..." already exists`.

### 4. Schema init

`app/db/schema.py:36-46` — existing code already gates on `eng.dialect.name != "sqlite"` (early-return). No change needed for Postgres compat. Future: move schema creation to Alembic (next section); `init_schema()` becomes Alembic-aware no-op when migrations present.

### 5. Alembic intro

```bash
uv add alembic
uv run alembic init migrations
```

`migrations/env.py`: import `Base` from `app.db.orm`, set `target_metadata = Base.metadata`. Use `DATABASE_URL_DIRECT` for offline migrations.

Generate initial migration:
```bash
uv run alembic revision --autogenerate -m "initial schema"
```

Add `embeddings` table manually (autogen won't know about pgvector types):

```python
# migrations/versions/XXXX_add_embeddings.py
from pgvector.sqlalchemy import Vector

op.execute("CREATE EXTENSION IF NOT EXISTS vector")
op.create_table(
    "embeddings",
    sa.Column("photo_id", sa.String, sa.ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("embedding", Vector(1536), nullable=False),
    sa.Column("embed_model", sa.String, nullable=False),
    sa.Column("year", sa.Integer, nullable=True),
)
op.execute("CREATE INDEX embeddings_hnsw ON embeddings USING hnsw (embedding vector_cosine_ops)")
op.create_index("embeddings_year_idx", "embeddings", ["year"])
```

### 6. Vector backend abstraction (keep ChromaDB alive as fallback)

Do **not** delete `app/chroma.py`. Instead introduce an interface and two impls.

```python
# app/vectordb/base.py
from typing import Protocol

class VectorBackend(Protocol):
    def upsert(self, photo_id: str, vec: list[float], embed_model: str, year: int | None) -> None: ...
    def query(self, qvec: list[float], n: int, year_filter: int | None = None) -> list[tuple[str, float]]: ...
    def distinct_embed_models(self) -> set[str]: ...
```

```python
# app/vectordb/chroma_backend.py — wraps existing app/chroma.py logic
class ChromaBackend:
    def __init__(self, path): ...   # PersistentClient + collection
    def upsert(self, photo_id, vec, embed_model, year):
        self.collection.upsert(ids=[photo_id], embeddings=[vec], metadatas=[{"year": year or 0, "embed_model": embed_model}])
    def query(self, qvec, n, year_filter=None):
        where = {"year": year_filter} if year_filter is not None else None
        r = self.collection.query(query_embeddings=[qvec], n_results=n, where=where)
        return list(zip(r["ids"][0], r["distances"][0]))
```

```python
# app/vectordb/pgvector_backend.py
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select
from app.db.orm import Embedding

class PgvectorBackend:
    def __init__(self, session_factory): self.sf = session_factory
    def upsert(self, photo_id, vec, embed_model, year):
        with self.sf() as s:
            stmt = pg_insert(Embedding).values(
                photo_id=photo_id, embedding=vec, embed_model=embed_model, year=year)
            stmt = stmt.on_conflict_do_update(
                index_elements=["photo_id"],
                set_={"embedding": stmt.excluded.embedding,
                      "embed_model": stmt.excluded.embed_model,
                      "year": stmt.excluded.year})
            s.execute(stmt); s.commit()
    def query(self, qvec, n, year_filter=None):
        with self.sf() as s:
            stmt = (select(Embedding.photo_id,
                           Embedding.embedding.cosine_distance(qvec).label("dist"))
                    .order_by("dist").limit(n))
            if year_filter is not None: stmt = stmt.where(Embedding.year == year_filter)
            return [(r.photo_id, r.dist) for r in s.execute(stmt).all()]
```

```python
# app/vectordb/__init__.py
def get_vector_backend(settings) -> VectorBackend:
    backend = os.getenv("VECTOR_BACKEND", "chroma")
    if backend == "chroma": return ChromaBackend(settings.chroma_path)
    if backend == "pgvector": return PgvectorBackend(SessionLocal)
    raise ValueError(backend)
```

Both backends return `list[tuple[photo_id, distance]]`. Caller code in `embed.py` + `query.py` never branches on backend.

Add ORM model `app/db/orm.py`:

```python
from pgvector.sqlalchemy import Vector

class Embedding(Base):
    __tablename__ = "embeddings"
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    embed_model: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

### 7. Embed step

`app/indexer/embed.py:79-83` (current ChromaDB `.upsert()`) → call `backend.upsert(photo_id, vec, embed_model, year)` via injected `VectorBackend`. Drop direct `app/chroma.py` import from embed step.

Embed model validation (`app/chroma.py:32-41` today): replace with `backend.distinct_embed_models()` at startup; assert current `settings.embed_model` matches existing data.

Keep `chroma_path` config (used when `VECTOR_BACKEND=chroma`). Add no new state.

### 8. Search query

`app/search/query.py:166` (current `collection.query()`) → call `backend.query(qvec, n, year_filter)`. Both backends return uniform `list[tuple[str, float]]`.

**Note:** pgvector cosine distance = `1 - cosine_similarity`. ChromaDB cosine returns same shape (lower = closer). Rank order identical. If any caller converts distance → similarity score, audit once.

### 9. Config

`app/config.py`: keep `chroma_path` (used when `VECTOR_BACKEND=chroma`). Keep `db_path` for local SQLite fallback. Add `vector_backend: str = "chroma"` setting if you prefer typed config over raw env reads.

## Verification

```bash
# 1. Start local Postgres or point at Supabase shadow project
export DATABASE_URL=postgresql+psycopg://...
export DATABASE_URL_DIRECT=postgresql+psycopg://...:5432/...

# 2. Apply migrations
uv run alembic upgrade head

# 3. Re-run indexer end-to-end on small set
uv run photos-index --step scan
uv run photos-index --step caption --limit 5
uv run photos-index --step embed

# 4. Query
uv run python -m app.search.query "kids at the beach"
# expect same top-K as ChromaDB run

# 5. API smoke
uv run uvicorn app.api.main:app --port 8000
curl 'http://localhost:8000/search?q=beach&limit=5' | jq
```

## Critical files

- `app/db/engine.py` (no change — existing SQLite guard correct)
- `app/db/schema.py` (no change — existing dialect guard correct)
- `app/db/types.py:10-34` (add `JsonCol` variant)
- `app/db/orm.py` Photo + PhotoPerson columns (swap `JSONString` → `JsonCol`); add `Embedding` model
- `app/db/upsert.py:15-92` (already dialect-aware, no change)
- `app/chroma.py` **(keep — wrapped by ChromaBackend)**
- `app/vectordb/{base,chroma_backend,pgvector_backend,__init__}.py` **(new)**
- `app/indexer/embed.py:32-83` (use VectorBackend)
- `app/search/query.py:166` (use VectorBackend)
- `app/config.py` (keep chroma_path; add vector_backend if typed)
- `pyproject.toml` (+`psycopg[binary]`, `pgvector`, `alembic`)
- `migrations/` **(new)**

## Risks

- **Connection pooling on serverless:** Supabase pooler (port 6543) = transaction mode, no `LISTEN/NOTIFY`, no prepared statements. Use psycopg3 + `?prepare_threshold=0` in URL.
- **Cold-start latency:** first query after idle ~200-500ms. Acceptable.
- **HNSW index build time:** on 100K rows ~minutes. Build once after bulk insert in cutover.
- **Embed model lock-in:** existing rows tied to model. Switching model = re-embed all.
