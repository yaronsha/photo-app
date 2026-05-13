# Vercel Deploy Config

Phase 5. Ship to Vercel.

## Repo layout (target)

```
family-photos-app/
├── app/
│   ├── api/            ← Vercel functions (Python)
│   ├── web/            ← React frontend (Vite)
│   ├── indexer/        ← step modules (imported by api/index_batch.py)
│   ├── db/, storage/, search/, config.py
├── migrations/         ← Alembic
├── vercel.json
├── requirements.txt    ← derived from pyproject (Vercel reads this)
├── pyproject.toml      ← canonical dep source for `uv` local
└── ...
```

## `vercel.json`

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "cd app/web && npm install && npm run build",
  "outputDirectory": "app/web/dist",
  "framework": null,
  "functions": {
    "api/index.py": {
      "runtime": "@vercel/python@4.3.1",
      "memory": 1024,
      "maxDuration": 60
    },
    "api/index_batch.py": {
      "runtime": "@vercel/python@4.3.1",
      "memory": 3008,
      "maxDuration": 300
    }
  },
  "_comment_maxDuration": "maxDuration > 300 requires Fluid Compute add-on in Vercel dashboard. Default to 300; raise only after observing real batch durations.",
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.py" },
    { "source": "/search",  "destination": "/api/index.py" },
    { "source": "/people",  "destination": "/api/index.py" },
    { "source": "/photo/(.*)", "destination": "/api/index.py" },
    { "source": "/thumb/(.*)", "destination": "/api/index.py" },
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ],
  "crons": [
    { "path": "/api/index-batch?step=google_metadata&limit=200", "schedule": "*/5 * * * *" },
    { "path": "/api/index-batch?step=caption&limit=30",          "schedule": "*/2 * * * *" },
    { "path": "/api/index-batch?step=embed&limit=200",           "schedule": "*/5 * * * *" },
    { "path": "/api/index-batch?step=thumb&limit=50",            "schedule": "*/3 * * * *" }
  ]
}
```

Vercel Python requires functions in `/api/` directory by convention. Create shim files:

```python
# api/index.py
from app.api.main import app  # FastAPI instance
# Vercel auto-detects ASGI
```

```python
# api/index_batch.py
from app.api.main import app
```

Actually with FastAPI on Vercel, single entry point is cleanest. Use one `api/index.py` and route everything through it. Differentiated cron function = nice-to-have for memory budget; can collapse to one if size budget allows.

## Frontend build

`app/web/vite.config.ts` — ensure base path `/` and proxy only used in dev:

```ts
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: {
      '/search': 'http://localhost:8000',
      '/people': 'http://localhost:8000',
      '/photo':  'http://localhost:8000',
      '/thumb':  'http://localhost:8000',
      '/api':    'http://localhost:8000',
      '/auth':   'http://localhost:8000',
    },
  },
})
```

`buildCommand` (in `vercel.json`) runs `npm run build` → `app/web/dist`. Vercel serves this as static + rewrites unknown paths to `index.html` (SPA fallback).

## `requirements.txt`

Vercel Python reads `requirements.txt` from project root, not `pyproject.toml`. Generate:

```bash
uv export --no-hashes --no-emit-project --frozen --no-dev -o requirements.txt
# strip indexer-only heavy deps if needed:
# pillow-heif, face_recognition, dlib, reverse_geocoder
```

Manual split if too big:

```bash
# requirements.txt (Vercel API)
fastapi
psycopg[binary]
pgvector
sqlalchemy
boto3
pyjwt[crypto]
openai
pillow
alembic

# requirements-local.txt (laptop only, not deployed)
pillow-heif
exifread
reverse-geocoder
face-recognition
```

Local install: `uv pip install -r requirements.txt -r requirements-local.txt`.

## Env vars (Vercel dashboard)

Production + Preview scopes:

```
DATABASE_URL                postgresql+psycopg://...@aws-...:6543/postgres?sslmode=require&prepare_threshold=0
DATABASE_URL_DIRECT         postgresql+psycopg://...@aws-...:5432/postgres   # Alembic only
VECTOR_BACKEND              pgvector                                          # or "chroma" for rollback
STORAGE_BACKEND             r2
R2_ACCOUNT_ID               ...
R2_ACCESS_KEY_ID            ...
R2_SECRET_ACCESS_KEY        ...
R2_BUCKET                   family-photos-...
SUPABASE_URL                https://....supabase.co
SUPABASE_JWT_SECRET         ...
VITE_SUPABASE_URL           https://....supabase.co   ← build-time, frontend
VITE_SUPABASE_ANON_KEY      ...                       ← build-time, frontend
ALLOWED_EMAILS              a@x.com,b@y.com
CRON_SECRET                 (random 32 bytes)
OPENAI_API_KEY              sk-...
```

`VITE_*` must be set as Build-time env vars (Vercel UI distinguishes).

## Database migrations on deploy

Alembic ≠ runtime. Add to build step OR run manually:

Option A — manual (safer): after each deploy, run locally:
```bash
DATABASE_URL=$DATABASE_URL_DIRECT uv run alembic upgrade head
```

Option B — auto in build: append to `buildCommand`:
```json
"buildCommand": "uv export ... && cd app/web && npm install && npm run build && cd ../.. && pip install alembic psycopg[binary] && alembic upgrade head"
```

Risk: build env lacks DB connectivity from build sandbox. Verify before relying.

Recommend **A** — small project, manual migration is fine.

## Plan tier

| Need | Hobby | Pro |
|---|---|---|
| Cron jobs | 2 max, daily fires only | 40, any cron expression |
| Max function duration | 60s | 300s default, 800s Fluid |
| Bandwidth | 100GB/mo | 1TB/mo |
| Function memory | 1024MB | 3008MB |
| Commercial use | no | yes |

**Pro recommended, Hobby viable.** Family photos = personal use, allowed on Hobby. Tradeoffs:

**Hobby path** (start here):
- Cron from outside Vercel: laptop `launchd`/`cron` or GitHub Actions hits `/api/index-batch?step=X` with `X-Cron-Secret` header. Sidesteps Vercel Cron 2-job + daily-fire limit.
- Small batches (5-10 photos/call) to stay under 60s function cap.
- Bandwidth = real risk. 100GB/mo. Monitor Vercel Usage dashboard month 1.
- Mitigate bandwidth before Pro upgrade:
  - Pre-generate 800px medium variant; lightbox uses medium, not fullsize. Cuts ~80% egress.
  - Or flip photo serving from proxy → presigned R2 URLs (zero Vercel egress, R2→browser direct). Loses per-request auth check; signed URL 5-min TTL bounds risk.

**Upgrade to Pro when:**
- Hit 70GB+ bandwidth in a month and don't want to add medium variant / presigned URLs
- Want Fluid Compute for faster cold starts
- Want Vercel Cron simplicity (no laptop dependency)

## External cron setup (Hobby)

**Option A — laptop `launchd`** (macOS):

```xml
<!-- ~/Library/LaunchAgents/com.familyphotos.cron.plist -->
<?xml version="1.0"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.familyphotos.cron</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>curl -s -X POST -H "X-Cron-Secret: $CRON_SECRET" "https://your-app.vercel.app/api/index-batch?step=caption&amp;limit=10"</string>
  </array>
  <key>StartInterval</key><integer>180</integer>
  <key>EnvironmentVariables</key>
  <dict><key>CRON_SECRET</key><string>...</string></dict>
</dict></plist>
```

`launchctl load ~/Library/LaunchAgents/com.familyphotos.cron.plist`

Requires laptop online. For backlog drain only, fine. After backlog → infrequent fires for new photos.

**Option B — GitHub Actions** (laptop-independent, free):

```yaml
# .github/workflows/index-cron.yml
name: Index cron
on:
  schedule:
    - cron: '*/5 * * * *'   # caption
    - cron: '*/10 * * * *'  # embed
  workflow_dispatch:
jobs:
  caption:
    if: github.event.schedule == '*/5 * * * *'
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -s -X POST -f \
            -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            "https://your-app.vercel.app/api/index-batch?step=caption&limit=10"
```

Free tier: 2000 min/mo, ~5min min cron interval. Curl call < 1s each, near-free use.

When using Hobby + external cron, **remove `crons` block from `vercel.json`** (or never add it).

## Deploy flow

```bash
# 1. Install CLI
npm i -g vercel

# 2. Link
cd family-photos-app
vercel link

# 3. Pull env vars locally
vercel env pull .env.vercel

# 4. Test build locally
vercel build

# 5. Preview deploy
vercel

# 6. Promote to production
vercel --prod
```

CI alternative: connect GitHub repo to Vercel project, push to `main` = auto-deploy.

## Verification

```bash
# 1. Preview build succeeds, function size < 250MB (check build logs)

# 2. Endpoints reachable
curl https://preview-xyz.vercel.app/search?q=test
# expect 401 (auth required)

# 3. Frontend loads
open https://preview-xyz.vercel.app/

# 4. Login flow
# email → magic link → redirect → /search renders

# 5. Cron dry-run
# Vercel dashboard → Crons → "Run now"
# verify response + DB row updated

# 6. Bandwidth + invocation count
# Vercel dashboard → Usage. Sanity-check daily numbers.
```

## Critical files

- `vercel.json` **(new)**
- `api/index.py` **(new, shim)**
- `api/index_batch.py` **(new, shim — optional separate function)**
- `requirements.txt` **(new, generated)**
- `app/web/vite.config.ts` (verify base + proxy)
- `app/web/package.json` (build script clean)
- `.vercelignore` **(new — exclude `data/`, `photos/`, `*.db`, `tests/`)**

## Risks

- **Function size 250MB** — biggest risk. Monitor `du -sh .vercel/output/functions/*`.
- **PgBouncer transaction mode** — no prepared statements, no session-scoped state. Add `?prepare_threshold=0`. SQLAlchemy 2.0 + psycopg3 = fine.
- **Cold-start UX** — first request after idle ~2s. Pro Fluid Compute reduces this.
- **Cron header verification** — Vercel sends `User-Agent: vercel-cron/1.0`; also accept `X-Vercel-Cron`. Don't rely on IP allowlist.
- **`.vercelignore` miss** — committing `data/photos.db` to repo = giant deploy. Triple-check.
