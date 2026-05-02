# Architecture

## Layers

```
┌─────────────────────────────────────────────────────┐
│  Frontend (vanilla HTML/JS/CSS)                     │
│  app/web/ — search box, grid, lightbox              │
└──────────────────────┬──────────────────────────────┘
                       │ fetch /search, /thumb, /photo, /people
┌──────────────────────▼──────────────────────────────┐
│  FastAPI (app/api/main.py)                          │
│  endpoints + thumbnail cache + path traversal guard │
└──────────┬─────────────────────────────┬────────────┘
           │                             │
┌──────────▼──────────┐         ┌────────▼────────┐
│  Search             │         │  Indexer        │
│  app/search/query   │         │  app/indexer/   │
│  vector + filters   │         │  pipeline steps │
└──┬───────────────┬──┘         └──┬─────────┬────┘
   │               │               │         │
   │ query embed   │ join          │ writes  │ writes
   ▼               ▼               ▼         ▼
┌──────────┐   ┌────────┐     ┌────────┐  ┌──────────┐
│ ChromaDB │   │ SQLite │     │ SQLite │  │ ChromaDB │
│ vectors  │   │ meta   │     │ meta   │  │ vectors  │
└──────────┘   └────────┘     └────────┘  └──────────┘
```

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+ · FastAPI · uvicorn |
| Metadata DB | SQLite (WAL mode, foreign keys ON) |
| Vector DB | ChromaDB (PersistentClient, cosine space) |
| Vision LLM | OpenAI `gpt-4.1-nano` (config: `caption_model`) |
| Embeddings | OpenAI `text-embedding-3-small` (config: `embed_model`) |
| Reverse geocode | `reverse_geocoder` (offline GeoNames) |
| EXIF | `exifread` + `pillow-heif` for HEIC |
| Face recognition _(Phase 2)_ | `face_recognition` (dlib) |
| Frontend | Vanilla HTML / CSS / JS — no framework |
| Env | `uv` + `pyproject.toml` |

## Decoupling Rules

1. **Search vs display** — `search()` returns `SearchResult[]`. Frontend chooses gallery / slideshow / lightbox.
2. **Search vs indexing** — search reads only what indexer wrote. New game = new query, not new index.
3. **Vector DB vs SQLite** — ChromaDB does semantic similarity only. Filter/sort/join in SQLite. Joined on `photo_id`.
4. **Provider abstraction** — caption + embed go through `app/indexer/providers/`. OpenAI is current sole impl; interface preserved so Anthropic etc. can be added.

## Data Storage

### `data/` layout (gitignored)
```
data/
├── photos.db         SQLite (metadata, faces, scores)
├── chroma/           ChromaDB persistent folder
├── sidecars/         {photo_id}.json from Google Takeout
├── thumbs/           generated 400x400 JPEG thumbnails
└── anchors/          (Phase 2) face anchor photos per person
```

### `photos/` layout
Merged from Google Takeouts — organized by year subfolder:
```
photos/
├── 2010/
├── 2024/
└── unknown/          no date metadata
```

## SQLite Schema

```sql
photos (
    id                          PK — sha256(file_bytes)[:16] (content hash)
    storage_path                UNIQUE — absolute path under photos_dir
    original_filename
    taken_at                    TIMESTAMP — EXIF or sidecar photoTakenTime
    location_name               "city, country_code" from reverse_geocoder
    lat, lng                    REAL
    caption                     TEXT — vision LLM output
    tags                        JSON array
    activities                  JSON array — visible verbs (dancing, eating)
    content_type                'photo' | 'document' | 'other'
    subject_type                portrait/group/landscape/food/...
    primary_focus               people/place/object/activity/unclear
    indoor_outdoor              indoor/outdoor/mixed/unclear
    setting_type                domestic_interior/restaurant/beach/...
    sharpness                   sharp/slightly_blurry/very_blurry
    face_clarity_score          INT 1-5 or NULL
    caption_schema_version      INT — bump to trigger re-caption
    happiness_score             REAL — Phase 3
    aesthetic_score             REAL — Phase 3
    description                 TEXT — user note from Google Photos
    google_people               JSON — raw Google face tags
    scan_indexed_at
    google_metadata_indexed_at
    caption_indexed_at
    vector_indexed_at
    face_indexed_at             — Phase 2
)

people (
    id          PK
    name
    family_id
)

photo_people (
    photo_id    FK photos
    person_id   FK people
    face_bbox   JSON [x,y,w,h] — Phase 2
    confidence  REAL — Phase 2 (NULL for Google-tagged)
    PK (photo_id, person_id)
)
```

Indexes: `taken_at`, `photo_people.person_id`, `content_type`, `subject_type`, `setting_type`.

## ChromaDB

- Collection name: `photos`
- Distance: cosine
- Embeddings = `caption + " " + " ".join(activities)`
- Metadata stored: `{"year": int}` only (sentinel `0` when `taken_at` NULL)
- Collection metadata records `embed_model` — mismatch raises on next embed run
- Always `upsert()`, never `add()`

## Search Flow

```
query → embed → chroma.query(top N=overfetch) → SQLite IN (...ids)
                                              + filter (date, person, content_type)
                                              → preserve chroma rank order
                                              → SearchResult[]
```

Browse mode (no query, only filters): straight SQLite `ORDER BY taken_at DESC`.

Detail in `app/search/query.py`. People filter supports `any` (default) and `all` modes.

## Frontend

Single-page vanilla. No framework. Three views toggled by header nav: search, games (placeholder), lightbox modal.

- `app/web/index.html` — markup
- `app/web/app.js` — fetch + render + lightbox + datepicker (~613 LOC)
- `app/web/style.css` — Playfair Display + Lora typography

Frontend size becoming substantial — see [REFACTOR_SUGGESTIONS.md](REFACTOR_SUGGESTIONS.md).

## Forkable Design

Each family = own `data/` + `config.json`. App code shared. No cross-family entanglement.

To fork:
1. Clone repo
2. New `config.json` (family_name, people, aliases)
3. New `data/` (created on first run)
4. Point `photos_dir` at family's collection
