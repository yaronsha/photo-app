# Family Photos AI App — Phase 1 Build Plan

## Context

`~/family-photos-app/` currently holds only design docs (`README.md`, `CLAUDE.md`, `FACE_RECOGNITION.md`) — no code yet. Goal of this plan: stand up **Phase 1** of the app (scan → caption → embed → search UI) end-to-end on a small test set (~50 photos), so the indexing pipeline, cost profile, and search quality can be validated before adding faces + games in Phase 2.

Design choices already locked in by the docs:
- Python + FastAPI backend, SQLite metadata, ChromaDB vectors, HTML/JS frontend.
- Idempotent indexer with `*_indexed_at` tracking; upsert semantics everywhere.
- Search and display fully decoupled; search returns `photo[]`.
- Scores (happiness, aesthetic) deferred — not on Phase 1 critical path.

User decisions from planning:
- **Scope**: Phase 1 only (no faces, no games).
- **Vision API**: OpenAI only for Phase 1 (captions + embeddings). Multi-provider dispatch deferred — provider-agnostic interface kept so Claude can be added later without refactor.
- **Photo ID**: content hash (`sha256(file_bytes)[:16]`), not path hash — survives moves/renames and dedupes identical files.
- **Photos source**: small test folder (~50 photos) to start; swap via `config.json` later.
- **Env**: `uv` + `pyproject.toml`.

---

## Repo Layout

```
family-photos-app/
├── pyproject.toml
├── uv.lock
├── config.json                 # family_name, data_dir, photos_dir, caption_model, people[]
├── .env.example                # ANTHROPIC_API_KEY, OPENAI_API_KEY
├── README.md                   # (exists)
├── CLAUDE.md                   # (exists)
├── FACE_RECOGNITION.md         # (exists)
├── data/
│   ├── photos.db               # SQLite (gitignored)
│   ├── chroma/                 # ChromaDB folder (gitignored)
│   └── anchors/                # Phase 2 — created empty now
├── photos/                     # symlink to test set (gitignored)
├── app/
│   ├── __init__.py
│   ├── config.py               # load/validate config.json + env
│   ├── db.py                   # SQLite connection, schema init, migrations
│   ├── chroma.py               # ChromaDB client + collection helpers
│   ├── models.py               # Photo, SearchResult dataclasses
│   ├── indexer/
│   │   ├── __init__.py
│   │   ├── cli.py              # `python -m app.indexer` entry (argparse: --step, --limit, --reindex)
│   │   ├── scan.py             # walk photos_dir, extract EXIF, upsert SQLite rows
│   │   ├── caption.py          # vision LLM → caption/tags; provider interface (OpenAI only Phase 1)
│   │   ├── embed.py            # caption+tags → embedding → ChromaDB upsert
│   │   └── providers/
│   │       ├── __init__.py     # get_caption_provider() + get_embed_provider() — returns OpenAI impl in Phase 1
│   │       └── openai.py       # OpenAI vision (gpt-4o) + text-embedding-3-small
│   ├── search/
│   │   ├── __init__.py
│   │   └── query.py            # semantic query: embed → chroma top-N → join SQLite → rank
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py             # FastAPI app: GET /search, GET /photos/{id}, GET /thumb/{id}
│   └── web/
│       ├── index.html          # search box + result grid
│       ├── app.js              # fetch /search, render thumbnails + captions
│       └── style.css
└── tests/
    ├── test_scan.py
    ├── test_caption.py         # mocks provider
    └── test_search.py
```

Gitignore: `data/`, `photos/`, `.env`, `__pycache__/`, `.venv/`.

---

## SQLite Schema (Phase 1 subset)

Implemented in `app/db.py`. Face columns declared now (NULL until Phase 2) so schema is stable.

```sql
CREATE TABLE IF NOT EXISTS photos (
  id                  TEXT PRIMARY KEY,       -- sha256(file_bytes)[:16] — content hash
  storage_path        TEXT NOT NULL UNIQUE,
  original_filename   TEXT NOT NULL,
  taken_at            TIMESTAMP,
  location_name       TEXT,
  lat                 REAL,
  lng                 REAL,
  caption             TEXT,
  tags                TEXT,                   -- JSON array
  happiness_score     REAL,                   -- Phase 3
  aesthetic_score     REAL,                   -- Phase 3
  scan_indexed_at     TIMESTAMP,
  caption_indexed_at  TIMESTAMP,
  vector_indexed_at   TIMESTAMP,
  face_indexed_at     TIMESTAMP               -- Phase 2
);

CREATE TABLE IF NOT EXISTS people (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  family_id  TEXT
);

CREATE TABLE IF NOT EXISTS photo_people (
  photo_id    TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  person_id   TEXT NOT NULL REFERENCES people(id),
  face_bbox   TEXT,                           -- JSON [x,y,w,h] — last detection if same person detected twice
  confidence  REAL,
  PRIMARY KEY (photo_id, person_id)
);

CREATE INDEX idx_photos_taken_at ON photos(taken_at);
CREATE INDEX idx_photo_people_person ON photo_people(person_id);
```

---

## Indexing Pipeline (Phase 1 steps)

Entry: `uv run python -m app.indexer --step {scan|caption|embed|all} [--limit N] [--reindex]`.

1. **scan** (`app/indexer/scan.py`)
   - Walk `photos_dir` (follow symlinks). Accept `.jpg .jpeg .png .heic`.
   - Register `pillow-heif` opener at module import so Pillow can read `.heic`.
   - Compute `id = sha256(file_bytes)[:16]` — content hash. Dedup: on collision with existing row, keep first `storage_path`, skip.
   - Extract EXIF via `exifread` or `Pillow.ExifTags`: `DateTimeOriginal`, GPS → lat/lng.
   - Reverse geocode: **skip for Phase 1** (leave `location_name` NULL; add in Phase 3 via offline DB to keep local-only).
   - Upsert into `photos`, stamp `scan_indexed_at = now()`.
   - Skip rows where `scan_indexed_at IS NOT NULL` unless `--reindex`.

2. **caption** (`app/indexer/caption.py` + `providers/`)
   - Phase 1: OpenAI only (`gpt-4o` vision). Provider interface stays so Claude can be added later.
   - Provider interface: `caption(image_path) -> {"caption": str, "tags": list[str]}`.
   - Prompt: ask for one descriptive sentence + up to 8 tags (people-agnostic — no names at caption time).
   - **Default `--limit 50`** (enforced in CLI) unless explicit flag. Docs mandate this.
   - Store `caption`, `tags` (JSON), stamp `caption_indexed_at`.
   - Skip rows with non-null `caption_indexed_at` unless `--reindex`.

3. **embed** (`app/indexer/embed.py`)
   - For rows with `caption IS NOT NULL` and `vector_indexed_at IS NULL` (or `--reindex`):
     - Build input text = `caption + " " + " ".join(tags)` so tag vocabulary participates in semantic space.
     - Embed via OpenAI `text-embedding-3-small`.
     - `collection.upsert(ids=[photo_id], embeddings=[vec], metadatas={"year": year_or_0})`. Use `0` sentinel when `taken_at` NULL so year-filter queries can choose to include/exclude dateless photos explicitly.
     - Persist `embed_model` name in Chroma collection metadata on first use; on subsequent runs assert match — refuse mixed-model corpus.
     - Stamp `vector_indexed_at`.

4. **all**: runs scan → caption → embed sequentially, preserving `--limit` semantics on caption step.

Idempotency test: running `--step all` twice in a row on the same photos dir must make zero API calls on the second run.

---

## Search Layer (`app/search/query.py`)

```python
def search(query: str, limit: int = 50, year_from: int | None = None, year_to: int | None = None) -> list[SearchResult]:
    # 1. embed query string (same provider as indexing)
    # 2. chroma.query(embeddings=[qvec], n_results=limit, where=...)
    # 3. SELECT * FROM photos WHERE id IN (...chroma_ids) — preserve chroma rank order
    # 4. attach distance as score
```

Phase 1 keeps query parsing simple: no LLM intent parsing, no person filtering (faces are Phase 2). Just semantic vector search + optional year filter passed as query params.

---

## FastAPI App (`app/api/main.py`)

Endpoints:
- `GET /search?q=<str>&limit=50&year_from=&year_to=` → JSON `{results: [{id, caption, taken_at, thumb_url, score}]}`
- `GET /thumb/{photo_id}` → streams a resized JPEG (generate on first request, cache under `data/thumbs/{id}.jpg`)
- `GET /photo/{photo_id}` → streams original file
- `GET /` → serves `app/web/index.html`
- Static mount: `/static` → `app/web/`

**Security:** both `/photo` and `/thumb` resolve `storage_path` via DB lookup. Before opening the file, `os.path.realpath(storage_path)` must start with `os.path.realpath(photos_dir)` — reject otherwise. Prevents path traversal even if DB tampered.

**Thumbnail cache dir:** `data/thumbs/` created on first write. Cache key = content-hash `photo_id`, so content changes implicitly invalidate.

Run: `uv run uvicorn app.api.main:app --reload --port 8000`.

---

## Frontend (`app/web/`)

Single-page, vanilla HTML + fetch:
- Search input, submit triggers `GET /search?q=...`.
- Grid of `<img src="/thumb/{id}">` with caption + date overlay.
- Click → full-res in `/photo/{id}`.

No framework. Keep it ≤150 LOC so Phase 2 can rewrite as needed.

---

## Config & Secrets

`config.json`:
```json
{
  "family_name": "Shapira",
  "data_dir": "./data",
  "photos_dir": "./photos",
  "caption_model": "gpt-4o",
  "embed_model": "text-embedding-3-small",
  "face_tolerance": 0.5,
  "people": []
}
```

`.env` (gitignored): `OPENAI_API_KEY`. `app/config.py` loads with `python-dotenv` and asserts key present at startup. (Anthropic key slot reserved for later phase.)

---

## Dependencies (`pyproject.toml`)

Runtime:
- `fastapi`, `uvicorn[standard]`
- `chromadb`
- `openai`
- `Pillow`, `pillow-heif`, `exifread` (or `piexif`) — EXIF + HEIC decode + thumbnail generation
- `python-dotenv`
- `pydantic` (FastAPI already pulls it; use for config model)

Dev:
- `pytest`, `pytest-asyncio`, `httpx` (TestClient)

---

## Critical Files to Create

| File | Purpose |
|---|---|
| `pyproject.toml` | deps + `[project.scripts]` entry `photos-index = "app.indexer.cli:main"` |
| `app/config.py` | load `config.json` + `.env`; validate; expose `Settings` singleton |
| `app/db.py` | `get_conn()`, `init_schema()`, row-factory helpers |
| `app/chroma.py` | `get_collection()` returning persistent client at `{data_dir}/chroma` |
| `app/indexer/scan.py` | walk + EXIF + upsert |
| `app/indexer/caption.py` | provider-dispatched captioning with `--limit` enforced |
| `app/indexer/embed.py` | text embed + chroma upsert |
| `app/indexer/providers/openai.py` | concrete vision + embed calls (Phase 1 sole provider) |
| `app/indexer/cli.py` | argparse entrypoint for `--step`, `--limit`, `--reindex` |
| `app/search/query.py` | semantic query + SQLite join |
| `app/api/main.py` | FastAPI routes + static mount |
| `app/web/{index.html,app.js,style.css}` | search UI |

No existing utilities in repo to reuse — this is a greenfield build.

---

## Verification

End-to-end sanity on ~50-photo test set:

1. `uv sync` — installs deps, creates `.venv`.
2. Copy ~50 photos into `./photos/` (or symlink). Put real `ANTHROPIC_API_KEY` in `.env`.
3. `uv run python -m app.indexer --step scan` → expect 50 rows in `photos.db`, all with `scan_indexed_at` set, EXIF where available.
4. `uv run python -m app.indexer --step caption --limit 50` → expect 50 captions; eyeball 5 for quality; check API cost in provider dashboard.
5. `uv run python -m app.indexer --step embed` → expect 50 rows in chroma collection; `vector_indexed_at` set on all.
6. **Idempotency**: re-run `--step all` → should make 0 API calls, 0 chroma writes (log should confirm "skipped N already-indexed").
7. `uv run uvicorn app.api.main:app --port 8000` → open `http://localhost:8000`.
8. Search queries to try: "beach", "happy group", "food", a location name. Results should be plausibly ranked.
9. `uv run pytest` — unit tests for scan (tmp dir + fake JPEG), caption (mocked provider), search (in-memory DB + stub embeddings).

Exit criteria for Phase 1: all 9 steps pass on a test set; search returns relevant hits for 3+ natural-language queries; re-running the indexer is free.

---

## Out of Scope (Phase 2+)

- `face_recognition` install, anchors, `photo_people` population.
- Games (`who is this?`, etc.).
- Happiness / aesthetic scores.
- Reverse geocoding for `location_name`.
- LLM intent parsing on queries.
- Deployment beyond `uvicorn --reload` on localhost.
