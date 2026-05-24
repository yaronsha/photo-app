# Cloudflare Deploy (supersedes Vercel)

Phase 5, Cloudflare edition. Replaces [deploy.md](deploy.md) (Vercel) — abandoned
because the Python API (boto3 + psycopg + pillow-heif + cryptography) exceeds
Vercel's 250 MB serverless function limit. A container has no such limit.

**Decision (2026-05):** API → Cloudflare Container; frontend → same Worker's
static assets (edge-cached = the CDN). One Worker fronts both. Single git-CD,
no CORS, no cross-project routing.

Verify config against live docs before trusting (Containers are beta, keys shift):
- https://developers.cloudflare.com/containers/
- https://developers.cloudflare.com/workers/static-assets/
- https://developers.cloudflare.com/containers/pricing/

## Architecture

```
                 ┌─────────────── one Cloudflare Worker ───────────────┐
  request ──────▶│  run_worker_first match?                            │
                 │   yes (/search /people /photo/* /thumb/* /auth/*    │
                 │        /api/*) ──▶ Worker code ──▶ Container (FastAPI)│
                 │   no  (/, /assets/*, /games, …) ──▶ ASSETS (edge CDN)│
                 │                                     SPA fallback ▶ index.html
                 └─────────────────────────────────────────────────────┘
        Container ──▶ Supabase (pgvector)   Container ──▶ R2 (presign 302)
```

- **Static** (React build) served from Cloudflare edge cache — the CDN. Photo
  bytes never touch the Worker/container: `/photo` `/thumb` return 302 → R2
  presigned (R2 egress free).
- **Container** is API-only. Scales to zero (`sleepAfter`); billed mostly on
  awake-hours. See cost model: `scripts/cf_container_cost.py`.
- Indexer + faces stay laptop CLI (Phase 4 still deferred — unchanged).

## Why Workers-with-Assets, not the Pages product

Pages is a separate project; wiring it to reach a container Worker needs
cross-project routing. Workers Static Assets puts the cached static build *on
the same Worker* that fronts the container — same CDN outcome, one deploy unit,
one `wrangler deploy`, native git builds. This is Cloudflare's current
recommendation for combined static + dynamic apps.

## Repo changes

| File | Change |
|---|---|
| `Dockerfile` | **new** — build the API image (python + uv, API-only) |
| `wrangler.jsonc` | **new** — container + durable_object binding + assets routing |
| `worker/index.ts` | **new** — Container class + forward API paths to it |
| `app/web/vite.config.ts` | `base: '/static/'` → `base: '/'` (assets now served at root) |
| `app/api/main.py` | re-apply the 2 fixes (below); container runs API-only |
| `.dockerignore` | **new** — exclude `data/ photos/ *.db .venv app/web/node_modules` |
| `package.json` (web) | ensure `npm run build` is clean (no `tsc &&` that can fail CI) |

### main.py fixes (re-apply — reverted with the Vercel PR)

1. **Guard startup mkdir** to `storage_backend == "local"` — with R2 the
   `data_dir/photos|thumbs` dirs are unused; avoids mkdir side effects.
2. **Register HEIF opener in the API path** (`pillow_heif.register_heif_opener()`
   before `_make_thumb`) — on-demand HEIC thumbs decode. No size limit here, so
   `pillow-heif` installs fine.

Container is API-only: frontend served by ASSETS, so the Worker never routes
`/` `/games` `/static` to the container. Those FastAPI routes go dead. Run the
container with `FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND=1` so `_ensure_dist()` does
not raise at import (it writes a stub into a writable container FS; never served
because the Worker never forwards `/` to the container).

## `Dockerfile` (API-only)

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app

# deps first (layer cache)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY config.json ./
RUN uv sync --frozen --no-dev

ENV STORAGE_BACKEND=r2 \
    VECTOR_BACKEND=pgvector \
    FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND=1
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

If a wheel needs system libs at runtime (watch the build): psycopg[binary] and
pillow-heif ship self-contained wheels — slim should suffice. face_recognition /
dlib are NOT installed (laptop-only); keep them out of the runtime deps used
here or split a deploy extra.

## `wrangler.jsonc`

```jsonc
{
  "name": "family-photos",
  "main": "worker/index.ts",
  "compatibility_date": "2026-05-01",

  "containers": [
    {
      "class_name": "ApiContainer",
      "image": "./Dockerfile",
      "instance_type": "standard-1",   // 4 GiB / 0.5 vCPU — safe for HEIC decode
      "max_instances": 2
    }
  ],
  "durable_objects": {
    "bindings": [{ "class_name": "ApiContainer", "name": "API_CONTAINER" }]
  },
  "migrations": [{ "tag": "v1", "new_sqlite_classes": ["ApiContainer"] }],

  "assets": {
    "directory": "app/web/dist",
    "binding": "ASSETS",
    "not_found_handling": "single-page-application",
    "run_worker_first": [
      "/search", "/people", "/photo/*", "/thumb/*", "/auth/*", "/api/*"
    ]
  }
}
```

`run_worker_first` is the routing split: listed paths invoke the Worker (→
container); everything else is served from the asset cache, with SPA fallback to
`index.html` for client routes like `/games`. Keep the list in sync with
`app/api/main.py` route prefixes.

## `worker/index.ts`

```ts
import { Container, getContainer } from "@cloudflare/containers";

export class ApiContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "5m";        // scale-to-zero idle tail — keep short (cost lever)
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only run_worker_first paths reach here; forward them to the container.
    // Single shared instance (family scale) — one name.
    return getContainer(env.API_CONTAINER, "api").fetch(request);
  },
};
```

(`@cloudflare/containers` is the helper package; `getContainer` resolves a
singleton instance by name. Confirm the import surface against current docs.)

## Env vars (Worker/Container secrets)

Set via `wrangler secret put <NAME>` (or dashboard). Same values as the Vercel
plan, minus anything Vercel-specific:

```
DATABASE_URL          postgresql+psycopg://...pooler:6543/postgres?sslmode=require&prepare_threshold=0
VECTOR_BACKEND        pgvector            # also baked in Dockerfile
STORAGE_BACKEND       r2                  # also baked in Dockerfile
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
SUPABASE_URL          https://<ref>.supabase.co   # auth = JWKS, derived from this
ALLOWED_EMAILS        a@x.com,b@y.com
OPENAI_API_KEY
FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND  1
```

Frontend build-time (`VITE_*`) are baked into the static build, not container
secrets — set them in the build environment (CD step / Workers Builds vars):

```
VITE_SUPABASE_URL
VITE_SUPABASE_ANON_KEY
```

`R2_ENDPOINT` not needed — derived from `R2_ACCOUNT_ID`.

## Build + deploy

Two artifacts each deploy: the static build (assets) and the container image.

```bash
# 1. frontend build → app/web/dist (the assets dir)
cd app/web && npm ci && npm run build && cd ../..

# 2. wrangler builds the Dockerfile, pushes to CF's registry, deploys Worker
npx wrangler deploy
```

First container deploy takes a few minutes to provision; until then API calls
error while the Worker is already live. Static assets serve immediately.

### CD (git push → deploy)

**Workers Builds** (native, Vercel-like): connect the repo in the Cloudflare
dashboard, set the build command to run the npm build then `wrangler deploy`,
add `VITE_*` build vars. Push to `main` = prod deploy; PRs get preview URLs.

Alternative: GitHub Actions with `cloudflare/wrangler-action` if you want more
control over the build matrix.

## Domain + auth

- Add a custom domain / route to the Worker in the dashboard.
- **Supabase → Auth → URL Configuration:** set Site URL + Redirect URLs to the
  Cloudflare domain (and preview domains) — else OAuth login bounces. (The prior
  Vercel `*.vercel.app` entry is now stale; replace it.)

## Verification

```bash
# 1. local container parity (before any cloud deploy)
docker build -t fp-api . && docker run --rm -p 8000:8000 --env-file <(...) fp-api
curl localhost:8000/search?q=test          # 401 (auth on) or results
curl localhost:8000/api/me                 # identity / auth_enabled

# 2. after wrangler deploy
curl https://<domain>/search?q=test        # 401 expected
curl https://<domain>/                     # index.html (cached static)
curl -I https://<domain>/assets/<hash>.js  # served from edge (cf-cache-status)

# 3. browser: login → search → photo renders (302→R2) → HEIC thumb renders
# 4. idle a few min → next request cold-starts (~seconds) → confirms scale-to-zero
```

## Cost

`uv run python scripts/cf_container_cost.py`. Light family ≈ $6/mo, active ≈
$13/mo, on `standard-1` with scale-to-zero. $5 of that is the Workers Paid base.
Trap: anything that keeps the container awake 24/7 (health-ping cron) → ~$35/mo.

## Critical files

- `Dockerfile`, `.dockerignore` **(new)**
- `wrangler.jsonc`, `worker/index.ts` **(new)**
- `app/web/vite.config.ts` (`base` → `/`)
- `app/api/main.py` (re-apply mkdir guard + HEIF opener; runs API-only)
- `pyproject.toml` / `uv.lock` (runtime deps; keep dlib/face out of the image)

## Risks

- **Containers are beta** — config keys (`instance_type`, helper imports) may
  shift. Verify against live docs each session.
- **Cold start** after idle: container boot + python import (~seconds). Family
  scale tolerates; do NOT fix with a keep-alive (flips cost to always-on).
- **Provisioning delay** on first deploy (minutes) — API errors until ready.
- **`base` flip** to `/`: local uvicorn-serving-dist would break, but local dev
  uses the vite dev server (proxy to :8000) so it's unaffected. Frontend is now
  served only by Cloudflare assets, never FastAPI.
- **vite base + run_worker_first must agree** with `app/api/main.py` route
  prefixes — add a prefix to the API, add it to `run_worker_first`.
```
