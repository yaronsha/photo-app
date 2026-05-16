# Compute: Vercel Functions (Batched) + Local CLI

Phase 4. Same indexer code runs two ways: CLI on laptop (today) **or** HTTP function on Vercel triggered by cron.

**Alternative driver: GitHub Actions** (free, easier logs, host-independent). Same `/api/index-batch` endpoint, just triggered by a workflow file on a cron schedule instead of Vercel Cron. Works on Vercel Hobby (which limits crons to 1) and avoids Vercel Pro requirement for indexer scheduling. Pick this if Vercel Cron costs/complexity become an issue. Auth via the same `CRON_SECRET` header.

```yaml
# .github/workflows/index.yml
on:
  schedule:
    - cron: "*/5 * * * *"
jobs:
  caption:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            "https://app.vercel.app/api/index-batch?step=caption&limit=30"
```

## Design

Each indexer step has three layers:

```
┌─ Driver layer ──────────────────────────────────────┐
│  cli.py            (loops + calls step.run)         │
│  api/index_batch.py (HTTP handler, calls step.run)  │
└────────────────────┬────────────────────────────────┘
                     │
┌─ Pure step layer ──▼─────────────┐
│  step.run(session, ids, settings) │ ← processes given IDs, returns
│  step.pending(session, limit)     │ ← returns next IDs needing this step
└──────────────────────────────────┘
```

`step.run` = pure: no CLI parsing, no global side effects, no progress bars. Idempotent. Returns count processed.

`step.pending(session, limit)` = SQL: `SELECT id WHERE <step>_indexed_at IS NULL LIMIT :limit`.

## Step interface

```python
# app/indexer/steps/base.py
from typing import Protocol
from sqlalchemy.orm import Session

class Step(Protocol):
    name: str
    def pending(self, session: Session, limit: int) -> list[str]: ...
    def run(self, session: Session, ids: list[str], settings) -> int: ...
```

Refactor each existing step into this shape:

| File today | After |
|---|---|
| `app/indexer/scan.py` | `app/indexer/steps/scan.py` — `run([], settings)` scans storage, returns count |
| `app/indexer/merge.py` | `app/indexer/steps/merge.py` — takes source folder arg, not ids |
| `app/indexer/google_metadata.py` | `app/indexer/steps/google_metadata.py` |
| `app/indexer/caption.py` | `app/indexer/steps/caption.py` — async, semaphore-bounded |
| `app/indexer/embed.py` | `app/indexer/steps/embed.py` |
| (new) | `app/indexer/steps/thumb.py` — generate + upload thumbs |

`scan` + `merge` don't fit batched model (they enumerate). Keep them CLI-only. Cron handles `caption`, `embed`, `google_metadata`, `thumb` — the per-photo idempotent steps.

## CLI driver

`app/indexer/cli.py` (refactor of today's `__main__`):

```python
STEPS = {
    "scan": ScanStep(), "merge": MergeStep(),
    "google_metadata": GoogleMetaStep(), "caption": CaptionStep(),
    "embed": EmbedStep(), "thumb": ThumbStep(),
}

def main():
    args = parse_args()  # --step, --limit, --folders, ...
    step = STEPS[args.step]
    settings = load_settings()
    with session_scope() as session:
        if args.step in ("scan", "merge"):
            step.run(session, [], settings)  # or with folders for merge
        else:
            ids = step.pending(session, args.limit or 10_000)
            step.run(session, ids, settings)
```

## HTTP driver

```python
# app/api/index_batch.py
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import require_cron
from app.indexer.cli import STEPS
from app.db.session import session_scope

router = APIRouter()

BATCHABLE = {"google_metadata", "caption", "embed", "thumb"}

@router.post("/api/index-batch")
def index_batch(step: str, limit: int = 50, _=Depends(require_cron)):
    if step not in BATCHABLE: raise HTTPException(400, f"step {step} not batchable")
    s = STEPS[step]
    settings = load_settings()
    with session_scope() as session:
        ids = s.pending(session, limit)
        if not ids: return {"processed": 0, "remaining": 0}
        n = s.run(session, ids, settings)
        remaining = len(s.pending(session, 1))  # poke for non-empty
    return {"processed": n, "remaining_at_least": remaining}
```

Mounted in `app/api/main.py`:

```python
from app.api.index_batch import router as index_batch_router
app.include_router(index_batch_router)
```

## Cron config — two modes

### Mode A — Vercel Cron (Pro plan)

`vercel.json`:

```json
{
  "crons": [
    { "path": "/api/index-batch?step=google_metadata&limit=200", "schedule": "*/5 * * * *" },
    { "path": "/api/index-batch?step=caption&limit=30",          "schedule": "*/2 * * * *" },
    { "path": "/api/index-batch?step=embed&limit=200",           "schedule": "*/5 * * * *" },
    { "path": "/api/index-batch?step=thumb&limit=50",            "schedule": "*/3 * * * *" }
  ]
}
```

Vercel Cron sends `X-Vercel-Cron: 1` header automatically. `require_cron` accepts either that or `X-Cron-Secret` (preview/manual triggers).

Tune `limit` so invocation stays < 300s Pro / 800s Fluid.

### Mode B — External cron (Hobby plan)

Hobby caps: 2 crons, daily fires only, 60s function timeout. Workaround = trigger from outside Vercel.

`vercel.json` has **no `crons` block**. Functions still respond to `POST /api/index-batch`, just driven externally.

**B1. GitHub Actions** (recommended — laptop-independent, free):

```yaml
# .github/workflows/index-cron.yml
name: Index cron
on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:
jobs:
  drive:
    runs-on: ubuntu-latest
    steps:
      - name: caption
        run: |
          curl -s -X POST -f \
            -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            "https://your-app.vercel.app/api/index-batch?step=caption&limit=10"
      - name: embed
        run: |
          curl -s -X POST -f \
            -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            "https://your-app.vercel.app/api/index-batch?step=embed&limit=50"
      - name: thumb
        run: |
          curl -s -X POST -f \
            -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            "https://your-app.vercel.app/api/index-batch?step=thumb&limit=20"
```

GitHub free = 5min min interval, 2000 min/mo, ample for this.

**B2. Laptop launchd** (macOS, requires laptop on):

```xml
<!-- ~/Library/LaunchAgents/com.familyphotos.caption.plist -->
<?xml version="1.0"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.familyphotos.caption</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-lc</string>
    <string>curl -s -X POST -H "X-Cron-Secret: $CRON_SECRET" "https://your-app.vercel.app/api/index-batch?step=caption&amp;limit=10"</string>
  </array>
  <key>StartInterval</key><integer>180</integer>
  <key>EnvironmentVariables</key><dict><key>CRON_SECRET</key><string>...</string></dict>
</dict></plist>
```

`launchctl load <plist>`. One file per step.

### Batch limits per mode

| Mode | Per-invoke limit suggestion | Per-day total | Notes |
|---|---|---|---|
| Pro Vercel Cron | caption=30, embed=200 | 21K caption, 57K embed | tune to 300s budget |
| Hobby external | caption=10, embed=50 | depends on cron freq | tune to 60s budget |

Backlog 100K caption math:
- Pro: ~5 days at 21K/day
- Hobby (10/call, every 5min) = 2880/day → ~35 days

Slower on Hobby. Acceptable for one-time backlog. After cutover, new-photo trickle handled either tier fine.

## Function size budget

Vercel Python function limit ~250MB unzipped. Heavy deps:

| Dep | ~Size | Needed in API fn? | Needed in indexer fn? |
|---|---|---|---|
| psycopg-binary | 10MB | yes | yes |
| pgvector | 1MB | yes | yes |
| boto3 + botocore | 50MB | yes | yes |
| openai | 5MB | no | yes |
| pillow | 15MB | maybe (thumb fallback) | yes |
| pillow-heif | 30MB | **no** | yes |
| exifread | 1MB | no | yes |
| reverse-geocoder | 30MB (data file!) | no | yes |
| face-recognition + dlib | 100MB+ | **no** | **skip on Vercel** |
| chromadb | gone | — | — |

Strategy: **two Vercel deployments**, or use Vercel's per-route `includeFiles`:

```json
{
  "functions": {
    "app/api/main.py":         { "runtime": "@vercel/python", "memory": 1024, "maxDuration": 60 },
    "app/api/index_batch.py":  { "runtime": "@vercel/python", "memory": 3008, "maxDuration": 300 }
  }
}
```

`maxDuration` > 300s requires Fluid Compute add-on enabled in Vercel dashboard. Start with 300; bump only if batches consistently approach limit.

Better: single requirements file per function via Vercel build hooks. Or: pre-build wheels.

Simpler interim: HEIC + face_recognition stay laptop-only. Vercel indexer handles `caption`, `embed`, `thumb`, `google_metadata`. Faces = laptop CLI only.

## Concurrency

Vercel may invoke same cron twice if previous run still in flight. Use Postgres advisory lock:

```python
def run(self, session, ids, settings):
    with session.connection().execution_options(isolation_level="AUTOCOMMIT"):
        got = session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": hash(self.name)}).scalar()
        if not got: return 0
        try:
            # ... process ids
        finally:
            session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": hash(self.name)})
```

Or: claim-by-update pattern (set `caption_indexed_at = '0001-01-01'` as "in progress" sentinel before processing).

## Verification

```bash
# 1. CLI still works
uv run photos-index --step caption --limit 5

# 2. HTTP endpoint manual
curl -X POST -H "X-Cron-Secret: $CRON_SECRET" \
  "http://localhost:8000/api/index-batch?step=caption&limit=5"
# expect {"processed": 5, "remaining_at_least": ...}

# 3. Idempotency
# run same batch twice; second returns processed=0 (all caption_indexed_at set)

# 4. Vercel preview deploy
# vercel deploy --prebuilt
# trigger cron manually via dashboard "Run now"
# check function logs

# 5. Backlog drain rate
# watch SELECT count(*) FROM photos WHERE caption_indexed_at IS NULL;
# should decrease over hours
```

## Critical files

- `app/indexer/steps/base.py` **(new)**
- `app/indexer/steps/{scan,merge,google_metadata,caption,embed,thumb}.py` (refactor)
- `app/indexer/cli.py` (driver wrapper)
- `app/api/index_batch.py` **(new)**
- `app/api/main.py` (include router)
- `vercel.json` (cron schedules)
- `app/db/session.py` (ensure `session_scope` is FastAPI-friendly)

## Risks

- **Function cold start** stacks: psycopg + boto3 + openai = ~2-3s cold. Cron tolerates this. User-facing endpoints feel it once per idle period.
- **OpenAI rate limits:** caption batch of 30 concurrent = 30 RPM. Tier 1 = 500 RPM. Fine. Embed = much higher limit.
- **Vercel cron drift:** schedules are UTC, not exact-to-second. Don't depend on alignment.
- **Partial failure:** mid-batch crash = some IDs marked done, others not. Next invocation picks up. Idempotency invariant must hold (caption step today: yes).
- **Hobby plan caps:** 1 cron job total on Hobby. Need **Pro** for multi-cron + Fluid + longer max duration.
