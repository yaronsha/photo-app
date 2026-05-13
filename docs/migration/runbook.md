# Cutover Runbook (One-Time)

Phase 6. Move existing data + flip to production. Run **after** Phases 1-5 verified.

## Pre-flight

- [ ] Phase 1 done: app runs locally against Supabase + pgvector on a small test set
- [ ] Phase 2 done: app runs locally against R2 for a small subset
- [ ] Phase 3 done: auth works locally
- [ ] Phase 4 done: batched indexer endpoint works locally + idempotent on rerun
- [ ] Phase 5 done: Vercel preview deploys, all endpoints respond
- [ ] Full backup of `data/photos.db` and `data/chroma/` (rollback)
- [ ] R2 bucket empty, Supabase schema applied (`alembic upgrade head`)
- [ ] Vercel env vars all set in Production scope

## Step 1 — Upload to R2

`thumbs/` and `sidecars/` are already id-named on disk (`{photo_id}.jpg`, `{photo_id}.json`) — rclone works directly. `photos/` are year-prefixed and original-named (`2020/IMG_1234.JPG`) — **must re-key** during upload using DB lookup to produce `photos/{photo_id}.{ext}`.

### 1a. thumbs + sidecars via rclone

```bash
brew install rclone
rclone config  # see storage.md §Bulk upload

# dry-run first
rclone sync data/thumbs   r2:family-photos-prod/thumbs   --dry-run --transfers 16
rclone sync data/sidecars r2:family-photos-prod/sidecars --dry-run --transfers 16

# real
rclone sync data/thumbs   r2:family-photos-prod/thumbs   --transfers 16 --progress
rclone sync data/sidecars r2:family-photos-prod/sidecars --transfers 16 --progress
```

### 1b. photos via re-keying Python script

```python
# scripts/upload_photos_to_r2.py
import os, mimetypes
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.orm import Photo
from app.storage import get_storage  # R2 backend

engine = create_engine(os.environ["SQLITE_PATH"])  # source SQLite (not Postgres yet)
storage = get_storage(...)  # R2 configured via env

with Session(engine) as s:
    for photo in s.scalars(select(Photo)):
        src = Path(photo.storage_path)  # absolute local path
        if not src.exists():
            print(f"missing: {photo.id}"); continue
        ext = src.suffix.lower()  # ".jpg" etc.
        key = f"photos/{photo.id}{ext}"
        mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
        storage.write_bytes(key, src.read_bytes(), content_type=mime)
```

Run:
```bash
SQLITE_PATH=sqlite:///data/photos.db \
STORAGE_BACKEND=r2 R2_BUCKET=family-photos-prod \
R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... \
uv run python scripts/upload_photos_to_r2.py
```

For 100K photos / 200GB on home connection: ~hours. Run overnight. Add resume-from-checkpoint (skip if `storage.exists(key)`) for restartability.

Verify counts:
```bash
rclone size r2:family-photos-prod
# compare per-prefix:
rclone size r2:family-photos-prod/photos
rclone size r2:family-photos-prod/thumbs
rclone size r2:family-photos-prod/sidecars
# vs:
du -sh data/photos data/thumbs data/sidecars
```

## Step 2 — Port metadata SQLite → Supabase Postgres

Use existing ORM + Core `insert()` for bulk. `bulk_insert_mappings` removed in SQLAlchemy 2.0 — use Core executemany pattern.

```python
# scripts/migrate_sqlite_to_postgres.py
import os, json
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session
from app.db.orm import Base, Photo, Person, PhotoPerson

src = create_engine(os.environ["SQLITE_URL"])           # sqlite:///data/photos.db
dst = create_engine(os.environ["DATABASE_URL_DIRECT"])  # postgres direct, not pooler

JSON_COLS = {
    Photo: {"tags", "activities", "google_people"},
    PhotoPerson: {"face_bbox"},
}

def row_to_dict(obj, model):
    d = {c.name: getattr(obj, c.name) for c in model.__table__.columns}
    # JSONString TypeDecorator returns Python objects on read.
    # For JSONB on Postgres, pass through as-is (psycopg serializes dict/list to JSONB).
    return d

BATCH = 1000
with Session(src) as ss, Session(dst) as ds:
    for Model in (Person, Photo, PhotoPerson):
        rows = [row_to_dict(o, Model) for o in ss.scalars(select(Model))]
        for i in range(0, len(rows), BATCH):
            ds.execute(insert(Model.__table__), rows[i:i+BATCH])
        ds.commit()
        print(f"{Model.__tablename__}: {len(rows)} rows")
```

```bash
SQLITE_URL=sqlite:///data/photos.db \
DATABASE_URL_DIRECT=postgresql+psycopg://...:5432/...?prepare_threshold=0 \
uv run python scripts/migrate_sqlite_to_postgres.py
```

JSONString → JSONB: source `JSONString` TypeDecorator returns Python list/dict on read; psycopg3 + JSONB column accept native dict/list directly via `insert()`. Test on 10 rows before full run (`LIMIT 10` in `select(Model)`).

## Step 3 — Rewrite `Photo.storage_path` → R2 keys

After Step 1b (upload script wrote `photos/{id}{ext}` keys to R2), update `storage_path` to match:

```sql
-- Supabase SQL editor, after Step 2 + 1b complete
UPDATE photos
SET storage_path = 'photos/' || id || lower(
  substring(storage_path from '\.[^.]+$')   -- extract original ext (incl. dot)
);
```

Verify rows match R2 keys exactly (case matters):
```bash
rclone lsf r2:family-photos-prod/photos | sort | head -5
psql "$DATABASE_URL_DIRECT" -c "SELECT storage_path FROM photos ORDER BY id LIMIT 5"
# every storage_path in DB must exist as R2 key. Spot-check 10 random.
```

If extension case differs (`.JPG` vs `.jpg`), align upload script + SQL update — both must use same casing. The upload script in Step 1b normalizes to `src.suffix.lower()`; the SQL `lower()` mirrors this.

## Step 4 — Build pgvector embeddings

ChromaDB → pgvector. Two paths:

**A. Re-embed from captions** (clean, costs ~$2 for 100K embeddings):
```bash
DATABASE_URL=... VECTOR_BACKEND=pgvector STORAGE_BACKEND=r2 ... \
  uv run photos-index --step embed
# embed step iterates photos where vector_indexed_at IS NULL
# null out vector_indexed_at first to force re-embed, OR clear new embeddings table to trigger
```

**B. Export ChromaDB → bulk insert**:
```python
# scripts/export_chroma_to_pgvector.py
import chromadb, os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.db.orm import Embedding

client = chromadb.PersistentClient(path="data/chroma")
coll = client.get_collection("photos")
dump = coll.get(include=["embeddings", "metadatas"])  # all rows

engine = create_engine(os.environ["DATABASE_URL_DIRECT"])
EMBED_MODEL = "text-embedding-3-small"
BATCH = 500
with Session(engine) as s:
    rows = [
        {"photo_id": pid, "embedding": vec,
         "embed_model": EMBED_MODEL,
         "year": (meta or {}).get("year")}
        for pid, vec, meta in zip(dump["ids"], dump["embeddings"], dump["metadatas"])
    ]
    for i in range(0, len(rows), BATCH):
        s.execute(insert(Embedding.__table__), rows[i:i+BATCH])
    s.commit()
```

**Recommend A** if captions trusted (simpler, no script). **B** if exact-vector reproducibility wanted.

After inserts: HNSW index already created via Alembic migration (see [db.md](db.md)). On 100K rows = minutes. Monitor Supabase dashboard for memory pressure during build.

**Rollback option:** if pgvector load fails or perf bad, set `VECTOR_BACKEND=chroma` in Vercel env, point at locally-hosted ChromaDB tunnel (cloudflared/tailscale) — or run the whole stack locally with `STORAGE_BACKEND=local VECTOR_BACKEND=chroma`. No code change.

## Step 5 — Smoke test against production

Still pointing local app at prod Supabase + prod R2 (not via Vercel yet):

```bash
DATABASE_URL=<prod-pooler> STORAGE_BACKEND=r2 R2_BUCKET=family-photos-prod ... \
  uv run uvicorn app.api.main:app --port 8000

# browse, search a handful of queries, verify:
# - photos load
# - thumbs load
# - search returns sensible results
# - people filter works
```

If anything broken: **stop**. Don't proceed to Vercel until parity confirmed.

## Step 6 — Deploy to Vercel production

```bash
# already linked
vercel --prod
```

Wait for build → green. Visit production URL. Login. Verify same checks as Step 5 via browser.

## Step 7 — Enable crons

Crons in `vercel.json` activate on production deploy automatically. Verify:

- Vercel dashboard → Crons → list shows 4 entries
- Wait for next scheduled fire
- Check function logs: `processed: N, remaining_at_least: M`
- DB: `SELECT count(*) FROM photos WHERE caption_indexed_at IS NULL` decreasing

If everything indexed already (Step 4), crons are no-ops until new photos arrive.

## Step 8 — Share with family

- [ ] Add family emails to `ALLOWED_EMAILS` in Vercel env
- [ ] Redeploy (env var changes need redeploy)
- [ ] Send each person the URL + brief instructions ("click magic link in email")
- [ ] First-use feedback: collect on shared note for 1 week

## Step 9 — Decommission laptop

Don't delete yet. Keep `data/photos.db.bak`, `data/chroma.bak`, `data/photos/` for 30 days.

After 30 days of no production issues + at least one bug-fix deploy:
- Archive `data/` to external drive
- `photos/` move to NAS / archive
- Repo continues to support local mode (env vars), useful for dev

## Adding new photos post-cutover

Two options:

**A. Always-laptop merge**: run `photos-index --step merge --folders ~/new-takeout` locally with `STORAGE_BACKEND=r2`. Merge step uploads bytes to R2 + writes Photo rows to Postgres. Then crons pick up caption/embed automatically.

**B. Upload tool**: small web upload UI that POSTs to a new `/api/upload` endpoint. Way more work. Defer.

Pick **A** for now. Document in `docs/DEVELOPMENT.md`.

## Rollback plan

If production breaks badly within first 24h:

1. Vercel dashboard → Deployments → previous green deploy → "Promote to Production"
2. Or: take Vercel project offline; family uses old laptop method
3. SQLite + ChromaDB backups still on laptop — restore by `cp .bak .`

R2 + Supabase = idempotent (rerun rclone, rerun migration script). No destructive ops in cutover.

## Verification checklist

- [ ] R2 object count = local file count for each prefix
- [ ] `SELECT count(*) FROM photos` Postgres == SQLite
- [ ] `SELECT count(*) FROM embeddings` == photo count (minus skip types)
- [ ] 5 sample searches return reasonable results
- [ ] 5 sample photo loads succeed via prod URL while logged in
- [ ] Crons run on schedule without errors for 1 hour
- [ ] Bandwidth/invocation usage within Vercel plan limits

## Risks

- **Egress cost spike on first family use**: 4 people loading 200GB of photos = much Vercel bandwidth. Pre-generate all thumbs (smaller). Don't auto-fullsize.
- **Magic link delivery**: Supabase default mailer may go to spam. Test with each family member.
- **DB connection limits**: Supabase free tier = 60 connections. Pooler = effectively unlimited via PgBouncer. Use pooler URL in app, direct only for Alembic.
- **Reindex blind spot**: if migration drops any photos (path mismatch, ext case sensitivity), search "loses" them silently. Cross-check counts before celebrating.
