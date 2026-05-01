# Agent Instructions — Family Photos AI App

Read README.md and FACE_RECOGNITION.md before starting any task.

## Planning Discipline

- When asked to create a plan, keep it high-level (goals, phases, deliverables) — do NOT include implementation details (specific function signatures, code snippets, file-level internals) unless explicitly requested.
- Put face recognition, indexing internals, and other technical deep-dives in separate MD files, not in CLAUDE.md or top-level PLAN.md.

## Verification Before Action

- Before running any multi-step job (embed, caption, batch test), confirm the plan with me and add/verify logging first.
- When analyzing screenshots or multi-file evidence, review ALL items before summarizing — do not generalize from one sample.
- Do NOT verify external APIs (e.g., Google Photos API) from memory — provide a link to current docs confirming availability.

## Autonomous Action Limits

- Do NOT add score thresholds, delete methods during refactors, or change search/embedding behavior without explicit approval.
- Keep SQLite transactions short in embed/caption pipelines to avoid lock contention.
- When the user asks 'which?' or a clarifying question, re-list the items — do not deflect.

## Communication Style

### Suggest, Don't Just Ask

- When the user describes a goal (e.g., 'quiz game platform'), propose 2-3 concrete options with tradeoffs BEFORE asking clarifying questions.

## Project Summary

Local-first family photo search + games app. Python + FastAPI + SQLite + ChromaDB + face_recognition. ~100K photos / 200GB. Personal project, forkable per family.

## Key Constraints

- **Local only** — no cloud dependencies at runtime. API calls only at index time (captions).
- **Idempotent indexer** — every index step must be safe to re-run. Use upsert, not insert. Check `index_version` and `*_indexed_at` columns before processing.
- **Small batch first** — when running AI caption calls, default to `--limit 50` unless explicitly told otherwise. API costs money.
- **Privacy** — do not suggest sending face data or full photos to cloud services.

## Architecture Rules

- Search and display are decoupled. Search returns `photo[]` + metadata. Never mix display logic into search.
- Games = query plugins. No new indexing for new game types.
- Scores (happiness, aesthetic) live in SQLite columns, not vector DB.
- Vector DB (ChromaDB) = semantic similarity only. Filtering/sorting = SQLite.
- Join search results on `photo_id` between SQLite and ChromaDB.

## Indexing Pipeline

Each step is independent and re-runnable:

```
0. merge      → app/indexer/merge.py → photos/ + data/sidecars/ (auto-runs scan after)
1. scan       → EXIF → SQLite
2. google_metadata → data/sidecars/{id}.json → SQLite (taken_at, lat/lng, description, photo_people)
3. location   → reverse_geocoder (offline) → SQLite (location_name)
4. caption    → Vision LLM + location hint → SQLite (caption, tags)
5. embed      → caption → ChromaDB vector
6. faces      → face_recognition → SQLite (photo_people)
7. scores     → LLM or model → SQLite columns
```

Track progress with `*_indexed_at` timestamps. Skip already-indexed unless `--reindex` flag passed.

### Google Takeout import

```bash
# Merge one or more Takeout folders (dedupes by SHA256, auto-runs scan)
uv run photos-index --step merge --folders ~/Downloads/Takeout/Google\ Photos ~/Downloads/"Takeout 2"/Google\ Photos

# Preview without copying
uv run photos-index --step merge --folders ~/Downloads/Takeout --dry-run

# Then run pipeline normally
uv run photos-index --step google_metadata   # enriches from sidecars, populates photo_people
uv run photos-index --step caption --limit 50
```

- `merge` only imports: `.jpg .jpeg .png .heic` — video/gif not yet supported in scan pipeline
- Dedupes against DB (populated by scan). Always run merge via CLI so scan runs atomically after.

Sidecars live at `data/sidecars/{photo_id}.json`. `google_metadata` step reads them to populate:
- `taken_at` — photoTakenTime (authoritative for old/scanned photos without EXIF)
- `lat` / `lng` — geoData (supplements EXIF)
- `description` — user-written note from Google Photos
- `photo_people` — Google face tags mapped to person IDs via `google_name_aliases` in config

## Face Recognition

See FACE_RECOGNITION.md for full details.

Key points for coding:
- Use supervised anchor matching, not clustering
- Anchors stored in `data/anchors/{person_id}/`
- Use `face_recognition.face_distance()` not just `compare_faces()` — store raw distance as confidence
- Default tolerance: 0.5 (strict). Make it configurable.
- Old photos (pre-1990): set `face_indexed_at` but store NULL person_id + low confidence — do not force a match.

## ChromaDB Usage

```python
# always upsert, never add
collection.upsert(
    ids=[photo_id],
    embeddings=[embedding],
    metadatas=[{"person_ids": "...", "year": 2010}]  # minimal metadata only
)

# query
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=50,
    where={"year": {"$gte": 2000}}  # pre-filter if needed
)
```

Keep ChromaDB metadata minimal — just fields needed for pre-filtering. Full record in SQLite.

## Config

```json
{
  "family_name": "Shapira",
  "data_dir": "./data",
  "photos_dir": "./photos",
  "caption_model": "gpt-4o",
  "embed_model": "text-embedding-3-small",
  "face_tolerance": 0.5,
  "people": [
    {"id": "yaron", "name": "Yaron Shapira"}
  ],
  "google_name_aliases": {
    "yaron shapira": "yaron",
    "נוי שפירא": "noa"
  }
}
```

`google_name_aliases` maps Google Photos free-text names (lowercased, Hebrew included) to person IDs. Used by `google_metadata` step to pre-populate `photo_people` from sidecar JSON.

## Common Tasks

**Add new person:**
1. Add entry to `config.json` people list
2. Add anchor photos to `data/anchors/{person_id}/`
3. Run `uv run photos-index --step faces --reindex` (re-runs all faces, minutes not hours)

**Re-run captions with new prompt:**
1. Update prompt in `app/indexer/caption.py`
2. Run `uv run photos-index --step caption --reindex --limit 50` (test first)
3. Run `uv run photos-index --step embed --reindex` (re-embed new captions)

**Add new game type:**
1. Create `app/games/{game_name}.py`
2. Implement `build_round(db, chroma) -> Round` 
3. Register in `app/games/__init__.py`
4. No indexing changes needed.

## Do Not

- Do not use `collection.add()` — always `upsert()`
- Do not run caption indexing on all photos without `--limit` flag first
- Do not store face images or embeddings in ChromaDB — SQLite only
- Do not add cloud face recognition (AWS Rekognition etc.) — privacy constraint
- Do not mix game logic into search or indexing layers
