# Indexer Module — Agent Notes

Loaded automatically when working under `app/indexer/`. Pairs with [docs/INDEXING.md](../../docs/INDEXING.md).

## Hot Rules

1. **Always upsert, never insert raw.** Every step must be safe to re-run.
2. **Stamp `*_indexed_at`** when work is done OR explicitly skipped (e.g. no sidecar). Never leave a row in "unprocessed" state without a reason.
3. **Skip predicate check first**, then heavy work. Cheap query > wasted API call.
4. **`--reindex` flag** must override the skip predicate but otherwise behave identically.

## SQLite Lock Discipline

WAL mode is on (`PRAGMA journal_mode=WAL`), engine `timeout=30`. SQLAlchemy 2.0 sessions are the API — `from app.db import get_session`. But:

- **Caption** (async, semaphore=6): each task opens its own `with get_session() as s:` context, executes a single short `UPDATE`, and exits. Concurrent writers serialize via SQLite's busy timeout. Do not share a single session across `await` points.
- **Embed** (sync, sequential): one session opened at the top, but `session.commit()` after every row — releases the lock so caption can interleave.
- Never `with session.begin(): ...long work...` in these steps. Short transactions only.

If you add a new step that runs concurrently with caption/embed, follow the same short-tx pattern.

## Schema Versioning

Pattern in `caption.py`:
```python
CAPTION_SCHEMA_VERSION = 2
```

Re-run condition:
```sql
WHERE caption_indexed_at IS NULL
   OR caption_schema_version IS NULL
   OR caption_schema_version < ?
```

**Bump the constant** whenever you change:
- The prompt text
- `PHOTO_ATTRIBUTES_SCHEMA` (output structure)
- The output → DB column mapping

Bumping triggers re-process of all rows next run, no `--reindex` needed.

## Caption Step Specifics

- OpenAI structured output via JSON Schema (`response_format=json_schema`, `strict=true`)
- Image resized to `MAX_SIDE=512` JPEG before send (cost reduction, OpenAI `detail=low`)
- Location hint: `location_name` if present, else `lat,lng` (4-decimal)
- `temperature=0`, `max_tokens=400`
- Conservative prompt: prefer `"unclear"` / `"other"` / `null` over guessing
- Captions never contain names — names attach via `photo_people` (Google tags or face match)

## Embed Step Specifics

- Embed text = `caption + " " + " ".join(activities)` — activities participate in semantic space
- Skip rows where `content_type IN ('document', 'other')` — keeps semantic space clean
- ChromaDB metadata = `{"year": int_or_0}` — minimal, only for pre-filter
- `assert_embed_model` records embed model in collection metadata; mismatch raises
- Reset embed model: delete `data/chroma/` (no migration path between models)

## Photo ID

`sha256(file_bytes)[:16]` — content hash, 16 hex chars (64 bits).

- Survives moves, renames, copies
- Two identical files → same ID → dedup wins automatically
- Two visually-identical files with different bytes → different IDs (cannot dedup these)
- Same path with different content → in `scan.py`, old row deleted, new inserted

## Sidecar File Naming

Google Takeout uses inconsistent naming. `merge.py:_find_sidecar` tries (in order):
1. `{photo_name}.supplemental-metadata.json`
2. `{photo_name}.json`
3. `{photo_stem[:-1]}.json` (last-char-truncated, for filename-length-limit cases)

If you see "no sidecar" for a high % of photos, inspect filenames manually first.

## Provider Interface

```python
provider.caption(image_path: Path, location_hint: str | None) -> dict[...]   # async
provider.embed(text: str) -> list[float]                                      # sync
```

Both go through `app/indexer/providers/__init__.py`. Currently OpenAI only — interface preserved for adding Anthropic later.

## Don't

- Don't use `collection.add()` — always `upsert()`
- Don't run `--step caption` without `--limit` for first runs (API costs)
- Don't write face encodings to ChromaDB — SQLite only
- Don't bypass the skip predicate by deleting `*_indexed_at` columns — use `--reindex`
- Don't add new ChromaDB metadata fields casually — vector DB stays minimal
- Don't add long transactions in caption/embed — lock contention

## Thumb Step Specifics

- 400×400 JPEG, `quality=85`, EXIF orientation applied via `ImageOps.exif_transpose`
- Reads source via `storage.read_bytes(photo.storage_path)`; writes `thumbs/{id}.jpg` via `storage.write_bytes`
- Idempotent: skip when `storage.exists(thumb_key)` unless `--reindex`
- Split error handling: `KeyNotFound` from source → permanent `skipped`; decode error → permanent `skipped`; storage write error → `transient_errors` (re-run picks it up)
- API `/thumb/` endpoint can still generate on-demand for misses, but `--step all` includes `thumb` so a freshly indexed corpus has thumbs pre-warmed

## When Adding a New Step

1. Create `app/indexer/{step}.py` with `run_{step}(reindex: bool = False, ...)`
2. Add `*_indexed_at` column to the `Photo` ORM model in `app/db/orm.py` (use `app/db/schema.py` `PHOTOS_ATTRIBUTE_COLUMNS` for non-essential cols, ALTER pattern handles older field DBs)
3. Wire into `cli.py` (`elif args.step == "...":`)
4. Update `--step all` if it belongs in default pipeline
5. Document in [docs/INDEXING.md](../../docs/INDEXING.md)
6. Add a test in `tests/test_{step}.py` (mock external APIs)
