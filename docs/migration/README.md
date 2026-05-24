# Migration: Local → Vercel + Supabase + Cloudflare R2

Index for the cloud migration. Each doc here is scoped + executable.

## Goal

Move the app from laptop-only (SQLite + ChromaDB + local files) to Vercel-hosted, accessible to family from anywhere. Local CLI workflow preserved.

## End-state stack

| Layer | Today | After |
|---|---|---|
| Hosting | `uvicorn` on laptop | Vercel (FastAPI Functions + static React) |
| Metadata DB | SQLite | Supabase Postgres (SQLite remains for local dev) |
| Vector DB | ChromaDB (local) | pgvector primary, ChromaDB rollback (via `VECTOR_BACKEND`) |
| Photo blobs | `photos/`, `data/thumbs/`, `data/sidecars/`, `data/anchors/` | Cloudflare R2 (LocalStorage remains for local dev) |
| Indexer | CLI on laptop | CLI (local) **or** Vercel Function batched via cron |
| Auth | none | Supabase Auth (Google OAuth, allowlist) |
| Photo serving | `FileResponse` local | 302 redirect to presigned R2 URL (default); byte proxy (fallback) |

## Decisions

- **Indexer host:** Vercel Functions, batched. Triggers = Vercel Cron (Pro) or GitHub Actions/laptop `launchd` (Hobby).
- **Photo serving:** proxy R2 bytes through Vercel (per-request auth check, hide R2 keys).
- **Auth:** Supabase Auth Google OAuth with email allowlist in env (`ALLOWED_EMAILS`). Auth is opt-in — leaving `SUPABASE_JWT_SECRET` unset disables enforcement (the local-dev rollback path).

## Phase order

| # | Phase | Doc | Status |
|---|---|---|---|
| 0 | Prep (accounts, env vars, doc skeletons) | this doc | ☐ |
| 1 | DB swap → Supabase Postgres + pgvector | [db.md](db.md) | ✅ |
| 2 | Storage abstraction + R2 backend | [storage.md](storage.md) | ✅ |
| 3 | Auth (Supabase Auth + JWT middleware) | [auth.md](auth.md) | ✅ |
| 4 | Compute refactor (dual CLI + HTTP batch) | [compute.md](compute.md) | ☐ deferred |
| 5 | Deploy → Cloudflare (container + Worker assets) | [cloudflare.md](cloudflare.md) | ☐ |
| 5~~old~~ | ~~Vercel deploy config~~ — abandoned (250 MB fn limit) | [deploy.md](deploy.md) | ✗ |
| 6 | Data cutover (one-time migration) | [runbook.md](runbook.md) | ✅ |

`R2_ENDPOINT` env var **not needed** — derived from `R2_ACCOUNT_ID` in `R2Storage.__init__`. Don't add it.

Do not skip ahead. Phase N depends on N-1 working locally before deploy.

## Phase 0 checklist

- [ ] Supabase project created, `pgvector` extension enabled in SQL editor (`CREATE EXTENSION IF NOT EXISTS vector;`)
- [ ] Cloudflare R2 account, bucket `family-photos-{family_id}` created, API token with R/W scope
- [ ] Vercel project linked to GitHub repo (don't deploy yet)
- [ ] Env var inventory captured (see below)
- [ ] `docs/migration/` skeletons present (this commit)

## Env var inventory

Local `.env` (added during migration):

```bash
# DB
DATABASE_URL=postgresql+psycopg://...supabase.co:6543/postgres?sslmode=require&prepare_threshold=0
DATABASE_URL_DIRECT=postgresql+psycopg://...supabase.co:5432/postgres   # Alembic only

# Vector backend
VECTOR_BACKEND=chroma            # or "pgvector"

# Storage
STORAGE_BACKEND=local            # or "r2"
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=family-photos-...
# R2 endpoint derived from R2_ACCOUNT_ID — no separate env var

# Auth
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=...            # frontend (VITE_SUPABASE_ANON_KEY for build)
SUPABASE_JWT_SECRET=...          # backend HS256 verify
ALLOWED_EMAILS=a@x.com,b@y.com

# Cron
CRON_SECRET=...                  # bearer for /api/index-batch (Vercel Cron auto-injects)

# Existing
OPENAI_API_KEY=...
```

Vercel dashboard: same set, override `STORAGE_BACKEND=r2` and `VECTOR_BACKEND=pgvector`.

## Critical invariant

App code must run **both** locally (today's CLI + uvicorn) **and** on Vercel. Differences = env vars only. No `if VERCEL: ...` branches.

Concretely: setting `STORAGE_BACKEND=local VECTOR_BACKEND=chroma` (+ SQLite `DATABASE_URL`) returns the app to today's exact behavior. This is the **rollback path** — if Vercel/Supabase/R2 stack ever fails, switch env vars and run locally. No code changes needed.

## Rough monthly cost

| Item | Cost |
|---|---|
| Vercel (hosting + cron + bandwidth) | $20/mo (Pro tier needed for >1 cron + Fluid + bandwidth headroom) |
| Supabase (DB) | $0 if data fits free tier, else paid plan |
| Cloudflare R2 (200GB) | ~$3/mo storage, $0 egress, $1/mo ops |
| OpenAI (ongoing trickle) | <$1/mo after initial backfill |
| **Total floor** | **~$25/mo** if Supabase free fits; higher if paid DB needed |

Initial backfill OpenAI cost (100K photos): ~$10-20 for captions (gpt-4.1-nano), ~$2 for embeddings.

## Where to read next

Start [db.md](db.md). Don't open storage until db smoke-tested.
