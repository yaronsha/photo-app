# Indexer Module — Agent Notes

Loaded automatically when working under `app/indexer/`. Pairs with [docs/INDEXING.md](../../docs/INDEXING.md).

## Hot Rules

1. **Always upsert, never insert raw.** Every step must be safe to re-run.
2. **Stamp `*_indexed_at`** when work is done OR explicitly skipped (e.g. no sidecar). Never leave a row in "unprocessed" state without a reason.
3. **Skip predicate check first**, then heavy work. Cheap query > wasted API call.
4. **`--reindex` flag** must override the skip predicate but otherwise behave identically.

## SQLite Lock Discipline

WAL mode is on (`PRAGMA journal_mode=WAL`), `timeout=30`. But:

- **Caption** (async, semaphore=6): tasks share one `conn`. Per-row `conn.commit()` releases lock immediately. Do not hold a transaction across `await` points without committing.
- **Embed** (sync, sequential): commits per row for the same reason — caption + embed can run concurrently in separate processes without locking each other out.
- Never `BEGIN; ...long work...; COMMIT;` in these steps. Short transactions only.

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

## When Adding a New Step

1. Create `app/indexer/{step}.py` with `run_{step}(reindex: bool = False, ...)`
2. Add `*_indexed_at` column in `db.py` (use `PHOTOS_ATTRIBUTE_COLUMNS` for non-essential cols, ALTER pattern handles it)
3. Wire into `cli.py` (`elif args.step == "...":`)
4. Update `--step all` if it belongs in default pipeline
5. Document in [docs/INDEXING.md](../../docs/INDEXING.md)
6. Add a test in `tests/test_{step}.py` (mock external APIs)
