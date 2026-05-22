# Roadmap

Replaces stale Phase-1 build plan (now mostly shipped).

## Status

### ✅ Phase 1 — Indexing + Search (shipped)
- Merge from Google Takeout (sha256 dedupe, year-folder layout, sidecars)
- Scan with EXIF + HEIC support
- Google metadata enrichment (taken_at, GPS, description, people from face tags)
- Offline reverse geocoding (`reverse_geocoder`)
- Vision LLM caption with structured JSON schema (caption + 9 attributes)
- Embedding → ChromaDB
- Hybrid search (vector + SQLite filter join)
- People filter (any/all mode)
- Date range filter (year/month/day)
- Lightbox viewer with caption, location, people, tags, description
- FastAPI app + vanilla SPA frontend
- Pytest suite

### 🚧 Cloud Migration — Phases 1-2 (in progress)

Goal: app deployable to Vercel with Supabase Postgres + Cloudflare R2 while still runnable on a laptop.

- ✅ **Phase 1 — DB swap → Supabase Postgres + pgvector** (shipped). See [docs/migration/db.md](migration/db.md).
- ✅ **Phase 2 — Storage abstraction + R2 backend** (shipped). `Photo.storage_path` repurposed from absolute filesystem path → backend-agnostic key. `app/storage/` package with `LocalStorage` + `R2Storage`, selected by `STORAGE_BACKEND` env var. Alembic migration `0002` rewrites pre-existing rows. See [docs/migration/storage.md](migration/storage.md).
- ☐ Phase 3 — Auth (Supabase Auth + JWT middleware). See [docs/migration/auth.md](migration/auth.md).
- ☐ Phase 4 — Compute refactor (dual CLI + HTTP batch). See [docs/migration/compute.md](migration/compute.md).
- ☐ Phase 5 — Vercel deploy config. See [docs/migration/deploy.md](migration/deploy.md).
- ☐ Phase 6 — Data cutover (one-time migration). See [docs/migration/runbook.md](migration/runbook.md).

### 🚧 Faces (next product phase)

Goal: detect faces locally, match against per-person anchors, populate `photo_people` for photos without Google tags.

See [FACE_RECOGNITION.md](../FACE_RECOGNITION.md) for design.

Tasks:
- [ ] Install `face_recognition` (CMake + dlib)
- [ ] Build `data/anchors/{person_id}/` per family member (3-5 photos spanning decades)
- [ ] Implement `app/indexer/faces.py`
  - Detect faces, generate encoding
  - Compare against all anchor encodings, pick best within `face_tolerance`
  - Decade-aware: prefer anchors within ±15 years of photo `taken_at`
  - Store raw distance as confidence
  - Pre-1990 photos: stamp `face_indexed_at` but skip match (low accuracy on B&W/scans)
- [ ] CLI: `uv run photos-index --step faces [--reindex] [--person <id>]`
- [ ] Skip photos already tagged from Google sidecar (don't overwrite higher-trust source)
- [ ] Update `--step all` to include faces

### 🎮 Games (product phase)

No new indexing. Each game = query plugin on existing data.

Tasks:
- [ ] `app/games/__init__.py` registry, `Round` dataclass
- [ ] `app/games/who_is_this.py` — random face-tagged photo + 3 wrong answers from other people
- [ ] `app/games/guess_year.py` — random photo, answer is decade
- [ ] `app/games/odd_one_out.py` — vector neighbors + 1 distant outlier
- [ ] `app/games/baby_match.py` — same `person_id` across decades
- [ ] FastAPI `/games/<type>/round` endpoint
- [ ] Frontend games view (currently placeholder)

### 📊 Scores (product phase)

LLM- or model-derived per-photo scores stored in SQLite columns.

Tasks:
- [ ] `happiness_score` REAL — emotional tone classifier
- [ ] `aesthetic_score` REAL — composition / quality model
- [ ] CLI step `--step scores` (idempotent, schema-versioned like caption)
- [ ] Search sort/filter by score (Browse-mode `ORDER BY happiness_score DESC`)

## Stretch / Later

- Multi-provider LLM dispatch (Anthropic Claude alongside OpenAI)
- LLM intent parsing on queries (extract people/dates/locations from natural language)
- Video / GIF support in scan + caption
- Memory cache for hot ChromaDB queries
- Album/collection grouping (vector clustering of similar photos)
- Mobile-friendly responsive layout
- Slideshow display mode
- Generation base output (curated set as input to other tools)
- LAN exposure with auth + CORS

## Out of Scope

- Cloud face recognition (privacy constraint)
- Multi-tenant deployment (forkable per family — one instance per family)
- Mass commercial use
- Strangers / 50+ unknown people corpus

## Open Questions

- When upgrading caption schema to v3, what new attributes are worth adding?
  Candidates: `season`, `time_of_day`, `weather`, `event_type` (birthday/wedding/holiday).
- Face match confidence: should photos below `face_tolerance` be stored with NULL `person_id` for review queue, or skipped entirely?
- Games: how to fairly randomize for kids vs adults? Difficulty tiers?
