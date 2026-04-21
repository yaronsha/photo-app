# Agent Instructions — Family Photos AI App

Read README.md and FACE_RECOGNITION.md before starting any task.

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
1. scan       → EXIF → SQLite
2. caption    → Vision LLM → SQLite (caption, tags)
3. embed      → caption → ChromaDB vector
4. faces      → face_recognition → SQLite (photo_people)
5. scores     → LLM or model → SQLite columns
```

Track progress with `*_indexed_at` timestamps. Skip already-indexed unless `--reindex` flag passed.

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
  "people": [
    {"id": "grandma", "name": "Grandma Sarah"}
  ],
  "caption_model": "claude-3-5-sonnet-20241022",
  "face_tolerance": 0.5
}
```

## Common Tasks

**Add new person:**
1. Add entry to `config.json` people list
2. Add anchor photos to `data/anchors/{person_id}/`
3. Run `python index.py --step faces --reindex` (re-runs all faces, minutes not hours)

**Re-run captions with new prompt:**
1. Update prompt in `app/indexer/caption.py`
2. Run `python index.py --step caption --reindex --limit 50` (test first)
3. Run `python index.py --step embed --reindex` (re-embed new captions)

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
