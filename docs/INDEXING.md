# Indexing Pipeline

CLI entry: `uv run photos-index --step <step> [--limit N] [--reindex]`
Implementation: `app/indexer/cli.py`

## Pipeline Steps

Each step is independent and idempotent. Track progress via `*_indexed_at` columns.

```
0. merge            → photos/ + data/sidecars/ (auto-runs scan after)
1. scan             → EXIF → SQLite
2. google_metadata  → data/sidecars/{id}.json → SQLite
3. location         → reverse_geocoder (offline) → SQLite (location_name)
4. pre_caption      → scan + google_metadata + location (convenience)
5. caption          → Vision LLM + location hint → SQLite (caption, attributes)
6. embed            → caption text → ChromaDB vector
7. faces            → face_recognition → SQLite (Phase 2 — not built)
8. scores           → LLM/model → SQLite (Phase 3 — not built)
all                 → 1+2+3+5+6
```

## Step Detail

### 0. merge — `app/indexer/merge.py`

Merge one or more Google Takeout folders into `photos/`.

```bash
uv run photos-index --step merge \
  --folders ~/Downloads/Takeout/Google\ Photos ~/Downloads/Takeout\ 2/Google\ Photos
```

- Accepted exts: `.jpg .jpeg .png .heic` (no video/gif yet)
- Dedupe by `sha256(file_bytes)[:16]` against existing DB rows + within run
- Organize destination by year (from sidecar `photoTakenTime` or "Photos from YYYY" folder)
- Sidecars copied to `data/sidecars/{photo_id}.json`
- `--dry-run` previews without copying
- Auto-runs `scan` after on success

### 1. scan — `app/indexer/scan.py`

Walk `photos_dir`, register `pillow-heif` opener, extract EXIF (`DateTimeOriginal`, GPS), upsert into `photos` table, stamp `scan_indexed_at`.

- Photo ID = `sha256(file_bytes)[:16]` — content hash, survives moves/renames
- Path collision (same path, different content) → delete old row, insert new
- Skip if `scan_indexed_at IS NOT NULL` unless `--reindex`

### 2. google_metadata — `app/indexer/google_metadata.py`

Read `data/sidecars/{photo_id}.json`. Populate:
- `taken_at` from `photoTakenTime` if EXIF empty (authoritative for old/scanned photos)
- `lat` / `lng` from `geoData` if EXIF GPS empty
- `description` (user note)
- `google_people` (raw JSON)
- `photo_people` rows via `google_name_aliases` map (case-insensitive, Hebrew supported)

Photos without sidecar → still stamp `google_metadata_indexed_at` (skip work next run).

People rows seeded from `config.json` first (idempotent upsert).

### 3. location — `app/indexer/location.py`

Batch reverse geocode `lat`/`lng` → `"city, country_code"`. Offline via `reverse_geocoder` (GeoNames). Run after `google_metadata` so sidecar GPS is available.

### 4. pre_caption

Convenience: `scan` + `google_metadata` + `location` in one. Use before `caption`.

### 5. caption — `app/indexer/caption.py`

Async with `Semaphore(CONCURRENCY=6)`. OpenAI structured output via JSON Schema (`PHOTO_ATTRIBUTES_SCHEMA`).

Resizes image to `MAX_SIDE=512` JPEG before sending (OpenAI cost reduction).

Populates: `caption`, `tags`, `activities`, `content_type`, `subject_type`, `primary_focus`, `indoor_outdoor`, `setting_type`, `sharpness`, `face_clarity_score`, `caption_schema_version`, `caption_indexed_at`.

Default `--limit 50`. Re-process when `caption_indexed_at IS NULL` OR `caption_schema_version < CAPTION_SCHEMA_VERSION` — bump the constant in `caption.py` to force re-run after prompt/schema change.

Location hint passed to model: `location_name` if present, else `lat,lng`.

Prompt rules: caption = one sentence, no names. Tags ≤ 8. Activities = verbs only, empty if posed. Conservative — prefer "unclear"/"other" over guessing.

### 6. embed — `app/indexer/embed.py`

Sync, sequential. Embeds `caption + " " + " ".join(activities)` so activity vocabulary participates in semantic space.

Skips rows where `content_type IN ('document', 'other')` — keeps semantic space clean.

ChromaDB upsert with `metadata={"year": int_or_0}`.

`assert_embed_model` records embed model name in collection metadata on first use; mismatch raises — refuse mixed-model corpus. Reset by deleting `data/chroma/`.

Commits SQLite per-row (`vector_indexed_at = now`) — short transaction → caption process can interleave without locking.

### 7. faces _(Phase 2 — not built)_

See [FACE_RECOGNITION.md](../FACE_RECOGNITION.md).

### 8. scores _(Phase 3 — not built)_

`happiness_score`, `aesthetic_score`. Stored in SQLite columns, not ChromaDB.

## Idempotency

Every step skips already-indexed rows by checking `*_indexed_at` columns. `--reindex` forces re-process.

Test: running `--step all` twice should make 0 API calls on second run.

## Schema Versioning

Pattern in `caption.py`:
```python
CAPTION_SCHEMA_VERSION = 2  # bump when prompt/schema/output structure changes
```

Re-run logic re-processes rows where `caption_schema_version < CAPTION_SCHEMA_VERSION`. Lets prompt updates ship without `--reindex` everything else.

Use the same pattern when adding versioned output to other steps.

## Concurrency Notes

- caption: async w/ `Semaphore(6)` — OpenAI API parallelism
- embed: sync, sequential — keeps SQLite transactions short, releases lock per row
- Both can run interleaved if both are short-tx
- See [app/indexer/CLAUDE.md](../app/indexer/CLAUDE.md) for full lock-contention rules

## Common Tasks

**Re-run captions with new prompt:**
```bash
# 1. Update prompt or schema in app/indexer/caption.py + bump CAPTION_SCHEMA_VERSION
# 2. Test small batch
uv run photos-index --step caption --reindex --limit 50
# 3. Run full set (omit --limit)
uv run photos-index --step caption --reindex
# 4. Re-embed updated captions
uv run photos-index --step embed --reindex
```

**Add a new person:**
1. Add to `config.json` people list
2. Add Google name alias(es) to `google_name_aliases`
3. `uv run photos-index --step google_metadata --reindex`
4. (Phase 2) Add anchors + `--step faces --reindex`

**Bring a fresh copy of photos into the system:**
```bash
uv run photos-index --step merge --folders /path/to/new/Takeout
# scan auto-runs
uv run photos-index --step pre_caption    # google_metadata + location
uv run photos-index --step caption --limit 50
uv run photos-index --step embed
```

## Idempotency Guarantees Reference

| Step | Skip condition | Forced by |
|---|---|---|
| merge | `id` already in DB or seen this run | (no force flag — re-run merges new files only) |
| scan | `scan_indexed_at IS NOT NULL` | `--reindex` |
| google_metadata | `google_metadata_indexed_at IS NOT NULL` | `--reindex` |
| location | `location_name IS NOT NULL` (and GPS present) | `--reindex` |
| caption | `caption_indexed_at NOT NULL AND caption_schema_version >= N` | `--reindex` or schema bump |
| embed | `vector_indexed_at IS NOT NULL` | `--reindex` |
