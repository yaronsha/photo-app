# API Reference

FastAPI app: `app/api/main.py`. Run via `uv run uvicorn app.api.main:app --reload --port 8000`.

Schema initialized on startup. Thumbnail cache dir created on startup.

## Endpoints

### `GET /`
Serves `app/web/index.html` (single-page UI).

### `GET /static/*`
Serves `app/web/` (CSS, JS).

### `GET /people`
List all known people from `config.json`.

**Response:**
```json
[
  {"id": "yaron", "name": "Yaron Shapira"},
  {"id": "noa",   "name": "Noa Shapira"}
]
```

### `GET /search`
Hybrid semantic + filter search.

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | _none_ | Natural language query. If empty/missing, falls back to browse mode (filter-only) |
| `limit` | int | `50` | Range 1-200 |
| `offset` | int | `0` | Skip this many results. Use with `has_more` for "Load more" pagination |
| `date_from` | ISO date `YYYY-MM-DD` | _none_ | Inclusive |
| `date_to` | ISO date `YYYY-MM-DD` | _none_ | Inclusive (server adds 1 day for half-open compare) |
| `person_id` | string (repeatable) | _none_ | Multiple `?person_id=yaron&person_id=noa` |
| `people_mode` | `any` \| `all` | `any` | `all` = photos containing every listed person |
| `include_docs` | bool | `false` | When false, excludes `content_type IN ('document','other')` |

**Behavior:**
- Empty query + no filters → returns `[]`
- Empty query + filters → browse mode (SQLite only, ordered by `taken_at DESC`)
- Non-empty query → vector search (overfetch 4× then filter, preserve chroma rank)

**Response:**
```json
{
  "results": [
    {
      "id": "abc123def456...",
      "caption": "Family gathered on a beach at sunset.",
      "taken_at": "2018-07-12T19:32:15+00:00",
      "thumb_url": "/thumb/abc123def456",
      "score": 0.78,
      "location_name": "Tel Aviv-Yafo, IL",
      "tags": ["beach", "sunset", "group"],
      "people": [{"id": "yaron", "name": "Yaron Shapira"}],
      "activities": ["walking"],
      "content_type": "photo",
      "subject_type": "group",
      "primary_focus": "people",
      "indoor_outdoor": "outdoor",
      "setting_type": "beach",
      "sharpness": "sharp",
      "face_clarity_score": 4
    }
  ],
  "has_more": false
}
```

`score` is `1.0 - cosine_distance` for vector search; `0.0` for browse mode.

`has_more` is `true` when more results exist beyond the current `offset + limit` window. Use with `offset` to implement "Load more" pagination.

### `GET /thumb/{photo_id}`
Returns 400×400 JPEG thumbnail. Generated lazily on first request, cached at `data/thumbs/{photo_id}.jpg`.

EXIF orientation applied (`ImageOps.exif_transpose`). Cache invalidates implicitly because `photo_id` is content hash.

### `GET /photo/{photo_id}`
Streams original file. Media type inferred from file suffix.

**Path traversal guard:** real-path of `storage_path` must start with real-path of `photos_dir`. Otherwise 403.

### `GET /photo/{photo_id}/info`
Full metadata for one photo. Returns everything in `photos` row plus joined `people`.

**Response fields:**
```
id, caption, taken_at, location_name, description, tags, activities,
people: [{id, name}], content_type, subject_type, primary_focus,
indoor_outdoor, setting_type, sharpness, face_clarity_score
```

## Error Responses

| Status | When |
|---|---|
| 400 | Invalid `date_from`/`date_to` format, invalid `people_mode` |
| 403 | Path traversal attempted on `/photo` or `/thumb` |
| 404 | Photo ID not in DB, or file missing on disk |

## Adding a New Endpoint

1. Add function in `app/api/main.py` with `@app.get(...)` / `@app.post(...)`
2. If photo file access — use `_resolve_photo_path()` to enforce traversal guard
3. If DB read — use `get_conn()` and close after; `row_to_dict()` to serialize JSON columns
4. Update this doc

## CORS / Auth

Currently none. Local-only deployment assumed. Add `CORSMiddleware` and auth before any LAN exposure.
