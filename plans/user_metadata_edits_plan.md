# User-Editable Photo Metadata — Backend & Schema Plan

## Context

Today every photo's metadata is owned by the indexer. Caption, tags, location, datetime, description, people are written by `scan` / `google_metadata` / `location` / `caption` steps and overwritten on re-runs. There is no way for a user to correct a wrong location, add a missed person, fix a date, or refine a caption without those edits being clobbered the next time the indexer runs.

This plan adds a user-edit layer that lives **alongside** indexer output — never destroying it. Reads return either:
- **Mode A — merged**: effective values plus a `meta` sidecar exposing `{original, user, edited_at}` per edited field, plus per-tag / per-person provenance for collections.
- **Mode B — user-preferred**: flat shape identical to today's API; user values shadow originals on conflict.

Indexer keeps writing to the original columns. User edits live in sidecar tables. A view computes `effective_*` for search and embed. Restore is reversible at any granularity.

Scope of this v1 (per user clarifications):
- **Scalars editable**: `caption`, `taken_at`, `location_name` + `lat` + `lng`, `description`.
- **Collections editable**: `tags` (add/remove), `people` (add/remove).
- **Skip in v1**: `activities` (LLM scaffolding).
- **Re-embed**: lazy only — PATCH sets `vector_indexed_at = NULL`; user runs `--step embed` to refresh.
- **UI**: understand only. Backend exposes both modes; frontend implementation deferred.

## Goals

1. Originals preserved in their existing columns. Indexer behavior unchanged.
2. User edits sparse, auditable, fully restorable per-field or wholesale.
3. Search and embed read **effective** values so search ranks the user's view of reality.
4. ChromaDB year metadata stays consistent with effective `taken_at`.
5. API backward-compatible: today's `/search` and `/photo/{id}/info` shape preserved as default; `meta` block is additive under `mode=merged`.

## Non-Goals

- No frontend implementation. Lightbox + edit UI deferred.
- No audit history (just current user value + restore).
- No multi-user / per-user attribution (single-family local app).
- No editing of LLM analysis fields (`subject_type`, `setting_type`, etc.) — derived, not facts.
- No alembic / migration framework — extend the existing `init_schema` pattern in `app/db.py`.

## Phases

### Phase 1 — Schema

Extend `app/db.py` `init_schema()`. SQLite has no `ADD COLUMN IF NOT EXISTS` — reuse the existing `PRAGMA table_info` + conditional `ALTER` pattern (already used for `PHOTOS_ATTRIBUTE_COLUMNS` at `app/db.py:83-86`).

New tables:
- `photo_user_edits` — one row per edited photo. Columns for each editable scalar (`user_caption`, `user_taken_at`, `user_lat`, `user_lng`, `user_location_name`, `user_description`) plus per-field `*_edited_at` timestamps so we can distinguish "user cleared this" from "user never touched this" and so the API can return `edited_at` per field.
- `photo_user_tags` — `(photo_id, tag, state, edited_at)` where `state ∈ {'added','removed'}`. Keyed `(photo_id, tag)`.

Extend `photo_people`:
- Add `source TEXT` ('google' | 'face' | 'user').
- Add `hidden_by_user INTEGER DEFAULT 0` for soft-delete of indexer-derived people.
- Add `added_at TIMESTAMP`.
- Backfill once: `UPDATE photo_people SET source='google' WHERE source IS NULL`.

New SQL view:
- `photos_effective` — `LEFT JOIN photo_user_edits` on photo_id and project `COALESCE(user_*, original_*)` as `effective_*` plus all original and user columns alongside.

Indexes:
- `idx_user_edits_edited_at` on `photo_user_edits(edited_at)`.
- `idx_photo_people_hidden` on `photo_people(hidden_by_user)`.

### Phase 2 — Read Path

Switch `app/search/query.py` reads from `FROM photos` to `FROM photos_effective`. WHERE/ORDER reference `effective_taken_at`, `effective_location_name`, etc. Browse mode date filters and date-ordering automatically respect user edits. Vector search SQL (the `WHERE id IN (...)` filter step) similarly references effective columns for date filtering.

Tags and people merge happens in Python (after the row fetch), not in SQL — keeps the view tractable:
- Tags: `auto_tags ∪ user_added_tags \ user_removed_tags`.
- People: `WHERE hidden_by_user = 0 OR (in mode A, include them with a flag)`.

`row_to_dict()` in `app/db.py` gains awareness of the `effective_*` and `user_*` columns and yields a clean `{value, original, user, edited_at}` per scalar field that the API layer can re-shape per mode.

### Phase 3 — Write Path (API)

New endpoints in `app/api/main.py`. All use a short SQLite transaction (no LLM/network calls inside the tx, per `app/indexer/CLAUDE.md` lock discipline). No CORS / auth (local-only assumption preserved; document the surface).

`PATCH /photo/{id}/metadata`
- Body fields: `caption`, `taken_at`, `lat`, `lng`, `location_name`, `description`, `tags_add`, `tags_remove`, `people_add`, `people_remove`.
- Semantics: omit = no change; `null` for a scalar = clear that user edit (revert to original).
- Upsert `photo_user_edits` row, set per-field `*_edited_at`.
- Tags: upsert into `photo_user_tags` with `state='added' | 'removed'`. Removing an "added" reverts to absent.
- People: insert with `source='user'` for additions; for removals of an existing auto-tagged person, set `hidden_by_user=1`. For removal of a `source='user'` row, delete it.
- Vector invalidation: if `caption` changed (set or cleared), `UPDATE photos SET vector_indexed_at = NULL, embed_schema_version = NULL WHERE id = ?`. If `taken_at` changed, also invalidate so Chroma `{"year": int}` metadata gets refreshed on next embed (year is derived from `effective_taken_at` — see Phase 4).
- Response: full photo info in the requesting client's preferred mode (`?mode=merged` or `?mode=user_preferred`, default `merged`).

`POST /photo/{id}/metadata/restore` (single-photo)
- Body: `{"fields": ["caption", "tags", "people"]}` OR `{"all": true}`.
- Per-field restore: NULL the matching `user_*` and `*_edited_at` columns. For `tags`: delete this photo's `photo_user_tags` rows. For `people`: delete `source='user'` rows AND `UPDATE photo_people SET hidden_by_user=0` for this photo.
- Caption restore re-invalidates vector. Date restore re-invalidates vector (year metadata).

`POST /metadata/restore-bulk`
- Body: `{"photo_ids": [...], "fields": [...] | "all": true}`.
- Same semantics as the single-photo route, applied in a loop inside one transaction. Useful for "I corrected 50 photos in error and want to undo all my edits in this batch."

`/search` and `/photo/{id}/info` updates
- Add `mode` query param. Default `merged`.
- Mode B (`user_preferred`): response shape **identical to today's** — `caption`, `location_name`, `tags: [str]`, `people: [{id,name}]`, etc., all using effective values. Backward-compatible.
- Mode A (`merged`): same top-level fields (effective values), plus a sibling `meta` object:
  ```json
  {
    "id": "...",
    "caption": "<effective>",
    "location_name": "<effective>",
    "tags": ["<effective merged list>"],
    "people": [{"id": "...", "name": "..."}],
    "meta": {
      "caption":       {"original": "...", "user": "...", "edited_at": "..."},
      "taken_at":      {"original": "...", "user": "...", "edited_at": "..."},
      "location_name": {"original": "...", "user": "...", "edited_at": "..."},
      "lat":           {"original": ..., "user": ..., "edited_at": "..."},
      "lng":           {"original": ..., "user": ..., "edited_at": "..."},
      "description":   {"original": "...", "user": "...", "edited_at": "..."},
      "tags": [
        {"value": "beach",       "source": "auto", "user_state": null},
        {"value": "vacation",    "source": "auto", "user_state": "removed"},
        {"value": "anniversary", "source": "user", "user_state": "added"}
      ],
      "people": [
        {"id": "yaron", "name": "Yaron Shapira", "source": "google", "hidden_by_user": false},
        {"id": "noa",   "name": "Noa Shapira",   "source": "user",   "hidden_by_user": false},
        {"id": "dan",   "name": "Dan",           "source": "google", "hidden_by_user": true}
      ]
    }
  }
  ```
- `meta` keys appear only for fields that have either an original or a user value (sparse). Only present when `mode=merged`.

### Phase 4 — Indexer Integration

`app/indexer/embed.py`:
- Read embedding source from `photos_effective`: `effective_caption + " " + " ".join(effective_activities)`.
- Year metadata for Chroma upsert derived from `effective_taken_at`.
- Lazy re-embed already triggered by `vector_indexed_at IS NULL` from PATCH endpoint. No new flag needed.

`app/indexer/google_metadata.py`, `app/indexer/location.py`, `app/indexer/caption.py`:
- **No changes.** Continue writing to the original columns. The user-edit layer shadows them transparently.

`app/indexer/scan.py`:
- **No changes.**

Phase 2 face recognition (future):
- Must `INSERT INTO photo_people (..., source) VALUES (..., 'face') ON CONFLICT DO NOTHING`.
- **Must not** reset `hidden_by_user` — a user removal is sticky. Document in `app/indexer/CLAUDE.md`.

### Phase 5 — Frontend (understanding only, no implementation)

For reference — what the frontend will need when implemented later:
- Lightbox sidebar gains an "Edit" affordance and a mode toggle (`merged` / `user_preferred`), persisted in `localStorage`.
- New `PATCH` / restore client calls. Today's `app/web/app.js` has zero non-GET fetches and no form pattern beyond the custom `MonthYearPicker` class — the edit UI will introduce the first write paths.
- Mode A renders effective values primary, original muted with a small badge ("auto: …"). Tags/people show source via chip color or icon; user-removed-but-originally-auto items show struck-through and re-clickable.
- Mode B renders identical to today (no badges, no struck-through items).
- The `meta` block is the data source for all mode-A presentation — the backend ships it ready for direct rendering, no client-side merge.

Backward-compat: cards in the search grid keep using `mode=user_preferred` (today's shape). The lightbox is the only consumer of `mode=merged`.

## Critical Files

- `app/db.py` — schema, `init_schema()`, `row_to_dict()`, `PHOTOS_ATTRIBUTE_COLUMNS` migration pattern. Add `photo_user_edits`, `photo_user_tags`, `photos_effective` view, `photo_people` extensions.
- `app/api/main.py` — new PATCH + restore endpoints; `mode` param on `/search` and `/photo/{id}/info`.
- `app/search/query.py` — switch `FROM photos` → `FROM photos_effective`; merge tags/people in Python; pass through user/original alongside effective into `SearchResult`.
- `app/indexer/embed.py` — read from `photos_effective`; derive year from `effective_taken_at`.
- `app/models.py` — extend `SearchResult` (or add a parallel `MetaBlock` dataclass) to carry the `meta` payload optionally.
- `app/indexer/CLAUDE.md` — add "do not reset `hidden_by_user`" rule for future face indexer.
- `docs/ARCHITECTURE.md` — schema section update (new tables, view).
- `docs/API.md` — document PATCH + restore endpoints, `mode` param.
- `docs/DEVELOPMENT.md` — note that user edits trigger lazy re-embed; mention `--step embed` after bulk edits.

## Verification

Backend:
1. `uv run pytest` — existing tests should pass (read paths via the new view must return identical shape in `mode=user_preferred`).
2. New unit tests in `tests/`:
   - `test_user_edits.py` — PATCH a caption → `mode=user_preferred` returns user value; `mode=merged` returns both. Restore → original returns.
   - `test_user_tags.py` — add tag, remove auto tag, verify merged + user-preferred shapes; verify dedup when auto re-derives a user-added tag.
   - `test_user_people.py` — extend, hide, restore. Verify `ON CONFLICT DO NOTHING` keeps `hidden_by_user` sticky on a `google_metadata` re-run.
   - `test_search_uses_effective.py` — edit `taken_at`, verify search ordering and date-filter use the user value.
   - `test_embed_invalidation.py` — PATCH caption sets `vector_indexed_at=NULL`; PATCH `taken_at` also invalidates (year refresh); PATCH location does not invalidate.
3. Manual smoke against running server:
   - Pick a photo. `PATCH /photo/{id}/metadata` with new caption + tag add. `GET /photo/{id}/info?mode=merged` returns effective + meta. `?mode=user_preferred` returns flat effective only. `POST /metadata/restore` with `{all:true}` returns it to original.
   - `uv run photos-index --step embed --limit 5` re-embeds the dirtied row; verify search query that should rank-improve now does.

Schema:
4. Drop into `sqlite3 data/photos.db` after `init_schema()`: `.schema photo_user_edits`, `.schema photo_user_tags`, `SELECT sql FROM sqlite_master WHERE name='photos_effective'`. Confirm `photo_people` has `source`, `hidden_by_user`, `added_at`. Run `init_schema()` twice — second run is a no-op (idempotent).

ChromaDB:
5. After PATCH `taken_at` from 2019 → 2020 and `--step embed`, query Chroma directly for that photo's metadata; confirm `{"year": 2020}`.

## Risks & Open Questions

- **`location.py` skip logic**: it currently skips photos where `location_name IS NOT NULL` unless `--reindex`. Editing the user's location does not impact this (user edit lives in sidecar). Fine.
- **`caption.py` schema-version re-runs**: when `CAPTION_SCHEMA_VERSION` is bumped, all auto captions are rewritten. User captions are unaffected (sidecar). Embed step's existing `embed_schema_version < caption_schema_version` predicate covers re-embed. Confirmed.
- **ChromaDB year staleness on `taken_at` edit**: explicitly handled by Phase 4 — embed step reads `effective_taken_at`, and PATCH invalidates the vector for both caption and date edits.
- **Concurrency**: PATCH writes are short tx; no LLM call inside. Safe with concurrent `--step caption` (also short tx) and `--step embed` (per-row tx).
- **Backward compat**: `mode=user_preferred` is the default to keep current frontend untouched. `meta` block is additive.
- **Open: tag normalization**. Should "Beach" and "beach" be treated as the same tag for dedupe? Recommend lowercase-on-write for `photo_user_tags.tag` and on auto tag comparison. Defer to implementation if it adds friction.
- **Open: bulk restore body size limits**. `POST /metadata/restore-bulk` — set a sane cap (e.g., 1000 photo_ids per call) and document it.
