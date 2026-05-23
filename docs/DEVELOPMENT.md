# Development

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv)
- Node 20+ + npm (for the React frontend)
- `OPENAI_API_KEY` (for caption + embed steps)
- _(Phase 2)_ CMake + dlib for `face_recognition`

## First-Time Setup

```bash
# 1. Install deps
uv sync

# 2. Env vars
cp .env.example .env.local
# edit .env.local — set OPENAI_API_KEY and any other overrides
# .env is never auto-loaded; pass ENV_FILE=.env.local when running commands
# (VS Code launch config already sets ENV_FILE automatically)

# 3. Config
$EDITOR config.json
# update family_name, people[], google_name_aliases

# 4. Photos
# Either: symlink `photos/` to existing collection
# Or:     run `--step merge --folders <takeout>`
```

## Run Commands

### Web app — production (FastAPI serves built React)
```bash
# 1. Build the frontend (once, or after frontend changes)
cd app/web && npm install && npm run build && cd ../..

# 2. Start FastAPI; serves app/web/dist/ at /static and dist/index.html at / and /games
uv run uvicorn app.api.main:app --reload --port 8000
# open http://localhost:8000
```

### Web app — frontend dev (HMR)
```bash
# Terminal 1
uv run uvicorn app.api.main:app --reload --port 8000

# Terminal 2 — Vite dev server, proxies /people /search /thumb /photo to :8000
cd app/web && npm run dev
# open http://localhost:5173
```

### Indexer
```bash
uv run photos-index --step <step> [--limit N] [--reindex]
```

Steps: `merge | scan | google_metadata | location | pre_caption | caption | embed | thumb | all`.
See [INDEXING.md](INDEXING.md) for full step detail.

### Tests
```bash
uv run pytest                       # all
uv run pytest tests/test_search.py  # one file
uv run pytest -k "person"           # by name
```

`tests/conftest.py` provides shared fixtures (`tmp_env`, `make_png`, `write_config`) — use them in new test files.

### Continuous Integration

GitHub Actions runs the full test suite on every push to `main` and every pull request. Workflow: [`.github/workflows/tests.yml`](../.github/workflows/tests.yml).

- Runner: `ubuntu-latest` · Python `3.14` (matches dev env) · `uv` for env
- Steps: `uv sync` then `uv run pytest -v`
- Watch runs: https://github.com/yaronsha/photo-app/actions/workflows/tests.yml

Local pre-push check:
```bash
uv run pytest                       # mirror what CI runs
```

## Project Layout

```
family-photos-app/
├── app/
│   ├── __init__.py
│   ├── config.py             — Settings model, env loading, paths
│   ├── db/                   — SQLAlchemy 2.0 ORM, lazy engine, sessions, upserts
│   ├── chroma.py             — collection helpers, embed_model guard
│   ├── models.py             — SearchResult dataclass
│   ├── indexer/
│   │   ├── cli.py            — argparse entry (photos-index)
│   │   ├── merge.py          — Google Takeout → photos/ + sidecars
│   │   ├── scan.py           — EXIF → SQLite
│   │   ├── google_metadata.py
│   │   ├── location.py       — reverse_geocoder offline
│   │   ├── caption.py        — async vision LLM, schema v2
│   │   ├── embed.py          — caption text → ChromaDB
│   │   ├── providers/
│   │   │   ├── __init__.py   — get_caption_provider, get_embed_provider
│   │   │   └── openai.py     — OpenAI vision + embeddings
│   │   └── CLAUDE.md         — indexer-specific gotchas
│   ├── search/
│   │   └── query.py          — vector search + SQLite filter join
│   ├── api/
│   │   └── main.py           — FastAPI endpoints
│   └── web/                  — Vite + React + TS + Tailwind frontend
│       ├── index.html        — Vite entry
│       ├── package.json
│       ├── vite.config.ts    — base /static/, dev proxy to :8000
│       ├── tailwind.config.ts — Gallery Pro theme tokens
│       ├── src/              — React source (layout/, features/, hooks/, api/)
│       └── dist/             — built output, served by FastAPI /static (gitignored)
├── tests/
│   ├── conftest.py           — shared fixtures (tmp_env, make_png)
│   ├── test_scan.py
│   ├── test_caption.py       — mocks provider
│   ├── test_embed.py
│   ├── test_search.py
│   ├── test_merge.py
│   ├── test_google_metadata.py
│   ├── test_location.py
│   └── test_api.py
├── .github/workflows/
│   └── tests.yml             — CI: pytest on push + PR
├── docs/                     — this directory
├── config.json               — per-family config
├── pyproject.toml            — deps + scripts entry
├── README.md
├── CLAUDE.md
└── FACE_RECOGNITION.md
```

## Config Reference (`config.json`)

```json
{
  "family_name":   "Shapira",
  "data_dir":      "./data",
  "caption_model": "gpt-4.1-nano",
  "embed_model":   "text-embedding-3-small",
  "face_tolerance": 0.5,
  "people": [
    {"id": "yaron", "name": "Yaron Shapira"}
  ],
  "google_name_aliases": {
    "yaron shapira": "yaron",
    "נוי שפירא": "noa"
  }
}
```

A legacy `photos_dir` key is ignored if present (Pydantic `extra="ignore"`), so existing configs do not need a hand-edit, but it can be removed for tidiness.

| Field | Notes |
|---|---|
| `family_name` | Used in UI header |
| `data_dir` | Single filesystem root: DB, photos (`data_dir/photos/`), thumbs, sidecars, anchors. Resolved relative to `config.json` if not absolute |
| `caption_model` | OpenAI vision model. `gpt-4.1-nano` is current default (cheap) |
| `embed_model` | Locked once corpus is embedded — change requires `data/chroma/` reset |
| `face_tolerance` | (Phase 2) face_recognition distance threshold (lower = stricter) |
| `people[]` | `{id, name}`, optionally `family_id` |
| `google_name_aliases` | Map Google Photos free-text name (lowercase, Hebrew OK) → `person_id` |

**Env vars (runtime):**

| Var | Default | Notes |
|---|---|---|
| `STORAGE_BACKEND` | `local` | `local` (filesystem under `data_dir`) or `r2` (Cloudflare R2) |
| `R2_ACCOUNT_ID` | — | Required when `STORAGE_BACKEND=r2` |
| `R2_ACCESS_KEY_ID` | — | Required when `STORAGE_BACKEND=r2` |
| `R2_SECRET_ACCESS_KEY` | — | Required when `STORAGE_BACKEND=r2` |
| `R2_BUCKET` | — | Required when `STORAGE_BACKEND=r2` |
| `ENV_FILE` | _(none)_ | Path to env file to load (e.g. `.env.local`). No file is loaded if unset — set explicitly, never rely on `.env` auto-loading |
| `VECTOR_BACKEND` | `chroma` | `chroma` (local ChromaDB) or `pgvector` (Postgres + pgvector) |
| `DATABASE_URL` | SQLite path | Postgres URL for app connections (pooler-safe) |
| `DATABASE_URL_DIRECT` | — | Direct Postgres URL for Alembic migrations (bypasses PgBouncer) |
| `OPENAI_API_KEY` | — | Required for caption + embed steps |
| `SUPABASE_URL` | — | Backend: Supabase project URL (e.g. `https://<ref>.supabase.co`). Used to derive the JWKS endpoint for ES256/RS256 verification — how current Supabase projects sign tokens. **Setting this (or `SUPABASE_JWKS_URL`) enforces auth.** |
| `SUPABASE_JWKS_URL` | derived from `SUPABASE_URL` | Backend: explicit JWKS endpoint override. Rarely needed |
| `SUPABASE_JWT_SECRET` | — | Backend: HS256 shared-secret verify key, for legacy/migrated projects that still sign with HS256. **Also enforces auth when set.** Unset *and* no `SUPABASE_URL` = local-dev rollback path (all endpoints open) |
| `ALLOWED_EMAILS` | — | Comma-separated email allowlist checked against the JWT `email` claim. Required when auth enforced |
| `CRON_SECRET` | — | Shared bearer for `/api/index-batch` (phase 4). Cron gate is bypassed when unset |
| `VITE_SUPABASE_URL` | — | Frontend build-time: Supabase project URL. Setting both this and the anon key enables the Google OAuth login gate |
| `VITE_SUPABASE_ANON_KEY` | — | Frontend build-time: Supabase anon public key |

## Common Tasks

### Add a new person
1. Add to `config.json` `people[]`
2. Add aliases to `google_name_aliases` (use exact Google name, lowercased)
3. `uv run photos-index --step google_metadata --reindex`
4. _(Phase 2)_ Add anchor photos + run `--step faces --reindex`

### Re-run captions after prompt change
1. Edit prompt or `PHOTO_ATTRIBUTES_SCHEMA` in `app/indexer/caption.py`
2. Bump `CAPTION_SCHEMA_VERSION` in same file
3. Test: `uv run photos-index --step caption --limit 50` (no `--reindex` needed — version bump triggers it)
4. Full: `uv run photos-index --step caption`
5. `uv run photos-index --step embed --reindex` to refresh vectors

### Reset everything
```bash
rm -rf data/photos.db data/chroma data/thumbs
# photos/ untouched, sidecars untouched
uv run photos-index --step scan          # re-build DB
# then google_metadata, location, caption, embed as needed
```

The schema is recreated automatically — `init_schema` (called on FastAPI startup and at the top of `scan`, `google_metadata`, and `location` indexer steps; `caption` and `embed` assume `scan` ran first) calls `Base.metadata.create_all` for the SQLAlchemy ORM models in `app/db/orm.py`.

### Database URL

Default: `sqlite:///{data_dir}/photos.db`. Override via `DATABASE_URL` (app) or `DATABASE_URL_DIRECT` (Alembic migrations). Engine is built lazily on first use and cached per-URL.

For local Postgres: start the container with `scripts/pg.sh start` (port 5432, DB/user/pass `photos`), then set `DATABASE_URL` + `DATABASE_URL_DIRECT` in `.env.local`. Run Alembic migrations with `ENV_FILE` + `DATABASE_URL_DIRECT` both explicit — no implicit `.env` loading:

```bash
ENV_FILE=.env.local DATABASE_URL_DIRECT=postgresql+psycopg://photos:photos@localhost:5432/photos \
  uv run alembic upgrade head
```

Migration `0002` rewrites absolute `storage_path` values to relative keys. If rows still have absolute paths, run without `STORAGE_MIGRATION_PREFIX` first — it auto-detects the prefix and tells you the correct value to pass.

### Add a new game type
1. Create `app/games/{game}.py` (module not yet implemented — see ROADMAP)
2. Implement `build_round(db, chroma) -> Round`
3. Register in `app/games/__init__.py`
4. No indexing changes needed — games are query plugins

## Testing Notes

- `test_caption.py` mocks the provider (no real API calls)
- `test_search.py` builds in-memory SQLite + stub embeddings
- Always run before committing logic changes

## Cost Awareness

- Caption: OpenAI vision API call per photo. For 100K photos, run small batch first.
- Embed: text-embedding-3-small is cheap but adds up. Idempotent so safe to re-run.
- Default `--limit 50` exists on caption to prevent accidental full runs.

## Logging

Each step prints summary line (counts + ETA where relevant). For deeper telemetry, watch caption.py timing log per photo.

## Database Inspect

```bash
sqlite3 data/photos.db
.headers on
.mode column
SELECT id, taken_at, content_type, caption FROM photos LIMIT 10;
```

ChromaDB has no easy CLI — use Python:
```python
from app.chroma import get_collection
col = get_collection()
print(col.count())
print(col.metadata)
```
