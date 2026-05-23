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
Returns a **302 redirect** to a short-TTL presigned URL for the 400×400 JPEG thumbnail. Thumbs are generated lazily on first request and cached at `thumbs/{photo_id}.jpg` in the configured storage backend.

EXIF orientation applied (`ImageOps.exif_transpose`). Cache invalidates implicitly because `photo_id` is a content hash. With `STORAGE_BACKEND=r2` the redirect points to R2 directly (no app bytes); with `STORAGE_BACKEND=local` it points to `/local/<key>` served as static files.

### `GET /photo/{photo_id}`
Returns a **302 redirect** to a short-TTL presigned URL for the original file. Media type negotiation happens at the storage layer.

**Storage-key guard:** `storage_path` must start with `photos/` and contain no `..` segments. Otherwise 403.

### `GET /api/me`
Returns the authenticated caller's identity (email, sub, whether auth is enforced). Useful for frontend sanity check.

```json
{"email": "user@example.com", "sub": "...", "auth_enabled": true}
```

### `POST /auth/exchange`
Fallback for cookie-based `<img>` auth (the default flow uses signed-URL redirects and doesn't need this). Validates the bearer in `Authorization: Bearer <jwt>` and returns `{"ok": true, "email": "..."}`. Frontend would set `sb_jwt` httpOnly cookie via this endpoint if it needed cookie-carrying `<img>` requests.

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
| 302 | Photo/thumb endpoints — redirect to presigned storage URL |
| 400 | Invalid `date_from`/`date_to` format, invalid `people_mode` |
| 401 | Missing / invalid / expired JWT (when auth enabled) |
| 403 | Allowlisted-email check failed, or path-traversal attempted on `/photo` or `/thumb`, or bad cron secret |
| 404 | Photo ID not in DB, or file missing on disk |

## Adding a New Endpoint

1. Add function in `app/api/main.py` with `@app.get(...)` / `@app.post(...)`
2. If photo file access — use `_resolve_photo_path()` to enforce traversal guard
3. If DB read — use `get_conn()` and close after; `row_to_dict()` to serialize JSON columns
4. Update this doc

## Auth

JWT verification via Supabase Auth (Google OAuth). All data endpoints (`/people`, `/search`, `/photo/*`, `/thumb/*`, `/api/me`, `/auth/exchange`) require `Authorization: Bearer <jwt>` or an `sb_jwt` cookie.

Tokens are verified by algorithm: **ES256/RS256** (current Supabase default) against the project's JWKS public keys, derived from `SUPABASE_URL`; **HS256** (legacy) against the `SUPABASE_JWT_SECRET` shared secret. Only configured trust material is honored, so the two paths can't be confused.

Auth is **opt-in**: with neither `SUPABASE_URL` (JWKS) nor `SUPABASE_JWT_SECRET` (HS256) set, `require_auth` is a no-op — preserves local-dev rollback path. Setting either + `ALLOWED_EMAILS` flips enforcement on.

Cron endpoints (`/api/index-batch`, phase 4) use `require_cron` instead — `Authorization: Bearer <CRON_SECRET>` or `X-Cron-Secret` header.

See [docs/migration/auth.md](migration/auth.md) for the full design.

## CORS

None configured — assumes same-origin frontend (Vercel static + functions). Add `CORSMiddleware` if API is split to a different domain.
