# Family Photos AI App

Local-first web app for families/friend groups to search, browse, and play with their photo collection using AI.

## What It Does

- **Natural language search** — "grandma at the beach", "that rainy trip to Rome", "everyone looks happy"
- **Person search** — find photos by named family member
- **Games** — Kahoot-style: "who is this?", "odd one out", "guess the year", "match the baby photo"
- **Flexible display** — gallery, slideshow, generation base — decoupled from search

## Non-Goals

- Not a commercial product
- Not designed for strangers — built for ~20 known people per family
- Not cloud-dependent — runs fully on a laptop

## Forkable Design

Each family gets their own `data/` folder. App code is shared. No entanglement between families.

```
/family-photos-app/
  app/               ← shared code
  data/
    photos.db        ← SQLite (metadata, faces, scores)
    chroma/          ← ChromaDB (vectors)
  config.json        ← family name, people list, data_dir
  photos/            ← symlink or path to actual photo collection
```

---

## Architecture

### Stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Metadata DB | SQLite |
| Vector DB | ChromaDB (local file) |
| Vision AI | Claude / OpenAI API (index time) |
| Face recognition | `face_recognition` lib (local) |
| Frontend | HTML + JS (simple start) |

### Data Flow

```
merge_takeouts.py       → photos/ (deduped) + data/sidecars/ (sidecar JSONs)
  → EXIF extract        → SQLite (date, GPS, location_name)
  → Google metadata     → SQLite (taken_at, description, photo_people from Google tags)
  → AI caption          → SQLite (caption text)
  → Embedding           → ChromaDB (semantic vector)
  → Face detection      → SQLite (person_id per face)
  → Scores              → SQLite (happiness_score, etc.)
```

Index once. Re-index is safe — idempotent, versioned per step.

### Search Flow

```
User query: "grandma at beach"
  → parse intent (LLM or keyword extract)
  → vector search on query embedding → top 50 candidates
  → filter by person_id, date, location
  → return ranked photo[]
```

Search and display are fully decoupled. Search returns `photo[]` + metadata. Display mode consumes that array however it wants.

### Games Are Query Plugins

No new indexing needed for games. Each game type = different query strategy on existing data.

| Game | Query |
|---|---|
| Who is this? | random face-tagged photo, wrong answers from other people |
| Odd one out | 3 nearest neighbors + 1 distant outlier via vector search |
| Guess the year | random photo, answer from EXIF |
| Match baby photo | same person_id, different decade |

---

## Scale

- ~100K photos / 200GB
- Vectors: ~400MB (ChromaDB local folder)
- SQLite: ~50MB
- Runs entirely on laptop, no internet required after indexing

---

## Build Phases

### Phase 1 — Full pipeline, no faces
1. Scan folder → SQLite (EXIF, paths)
2. AI captions on small batch (50 photos) → tune prompt → run on all
3. Embed captions → ChromaDB
4. Basic search UI

### Phase 2 — Faces + Games
1. Install `face_recognition` (see [FACE_RECOGNITION.md](FACE_RECOGNITION.md))
2. Collect anchors per person, run matching
3. First game: "who is this?"

---

## Key Design Decisions

- **Scores at index time** — `happiness_score`, aesthetic score computed once on upload, stored as SQLite columns. Query time = free SQL sort.
- **Supervised face matching** — not clustering. 20 known people → anchor photos per person → match all detected faces against anchors.
- **Hybrid search** — vector similarity for semantic, SQLite for filter/sort/exact. They join on `photo_id`.
- **Local face recognition** — privacy. Family photos stay on-device.
- **Games need no re-indexing** — all game mechanics use data already in the index.

---

## SQLite Schema (simplified)

```sql
photos (
  id, storage_path, original_filename,
  taken_at, location_name, lat, lng,
  caption TEXT,
  tags JSONB,
  happiness_score REAL,
  aesthetic_score REAL,
  description TEXT,                    -- user note from Google Photos
  google_people TEXT,                  -- raw Google face tags JSON
  scan_indexed_at TIMESTAMP,
  caption_indexed_at TIMESTAMP,
  vector_indexed_at TIMESTAMP,
  face_indexed_at TIMESTAMP,
  google_metadata_indexed_at TIMESTAMP
)

people (id, name, family_id)

photo_people (photo_id, person_id, face_bbox, confidence)
```
