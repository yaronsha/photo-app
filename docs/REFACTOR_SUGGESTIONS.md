# Refactor Suggestions

Observed during the doc-rewrite pass. Each item: **what** + **why** + **suggested action**. None are blocking — file order is rough priority.

---

## 1. Dedup `_sha256_id` between `merge.py` and `scan.py`

**What:** Identical 6-line `_sha256_id(path: Path)` defined in both `app/indexer/merge.py` and `app/indexer/scan.py`.

**Why:** Two definitions = drift risk. If hash length or chunk size changes in one place, photo IDs diverge silently.

**Action:** Move to `app/indexer/_hash.py` (or `app/indexer/__init__.py`). Both modules import from there.

---

## 2. Empty `scripts/` directory

**What:** `scripts/` contains only `__pycache__`. Original `scripts/merge_takeouts.py` was promoted into the CLI (`--step merge`).

**Why:** Empty dir confuses readers about whether something belongs there. PLAN.md still referenced the old script path.

**Action:** Delete `scripts/`. Future one-off utilities can go into a clearly named `tools/` or just be CLI subcommands.

---

## 3. Unused `Photo` dataclass in `app/models.py`

**What:** `Photo` dataclass declared but unused — search returns dicts via `row_to_dict`. Only `SearchResult` is read.

**Why:** Dead code. Reader assumes it's the canonical photo type.

**Action:** Either (a) delete `Photo` entirely, or (b) make it the canonical row type and convert `row_to_dict` callers to construct it. (a) simpler.

---

## 4. Frontend monolith (app.js 613 LOC, style.css 982 LOC)

**What:** Single-file vanilla JS handles search, filters, chip rendering, datepicker (`mypicker`), lightbox, navigation. CSS likewise.

**Why:** README boasts <150 LOC frontend; reality is 4× that and growing. Adding games view will make it worse. Vanilla is fine, single-file is not.

**Action (when adding games view):**
```
app/web/
├── index.html
├── style.css                  → split: _base.css, _search.css, _lightbox.css, _games.css (concatenate at build OR import via CSS @import)
├── js/
│   ├── main.js                — entry, view router
│   ├── search.js              — query + filters + grid
│   ├── lightbox.js            — modal viewer
│   ├── datepicker.js          — mypicker
│   └── api.js                 — fetch wrappers
```

ES modules (`<script type="module">`) — no bundler needed.

---

## 5. Async/sync inconsistency: `caption` vs `embed`

**What:** `caption.py` uses `asyncio` + `Semaphore(6)`. `embed.py` is sync, sequential, commits per row.

**Why:** Mostly intentional (caption = parallel API calls; embed = short SQLite-tx + Chroma upsert), but undocumented and surprising.

**Action:** Either:
- Add comment at top of `embed.py` explaining the sequential design
- Or make embed async too (gather batches of N), keeping per-batch SQLite commits

Either is fine. Just pick one and document.

---

## 6. Provider split for caption vs embed

**What:** `app/indexer/providers/__init__.py` returns the same `OpenAIProvider` for both `get_caption_provider()` and `get_embed_provider()`.

**Why:** Today both are OpenAI. If/when adding Anthropic vision, you'll want caption=Anthropic + embed=OpenAI (Anthropic has no embeddings). Current code couples them.

**Action:** Split provider interfaces (already separate functions — good). When adding 2nd provider, introduce `caption_provider` + `embed_provider` config keys, dispatch independently.

---

## 7. Schema migrations inline in `db.py`

**What:** `init_schema()` does `CREATE TABLE IF NOT EXISTS` + a hand-rolled `ALTER TABLE` loop using `PHOTOS_ATTRIBUTE_COLUMNS` list.

**Why:** Works fine for Phase 1 evolution. Will become unwieldy with Phase 2/3 face + score columns + indexes.

**Action (when migration count > 5):** Move to `app/migrations/` with numbered SQL files (`001_initial.sql`, `002_add_caption_attrs.sql`, ...) + a migrations table tracking applied versions. Or adopt `alembic` if heavier needs emerge.

---

## 8. Hardcoded constants in `providers/openai.py`

**What:** `MAX_SIDE = 512`, `temperature=0`, `max_tokens=400`, `image_url.detail = "low"` all hardcoded.

**Why:** Tuning these requires code edit. `MAX_SIDE` especially affects cost vs caption quality.

**Action:** Promote to config (`config.json` → `caption.image_max_side`, `caption.detail`, `caption.max_tokens`). Defaults stay sane.

---

## 9. `caption_schema_version` — good pattern, replicate elsewhere

**What:** Bumping `CAPTION_SCHEMA_VERSION` in `caption.py` triggers re-process without `--reindex`. Clean idempotent versioning.

**Why:** Same problem will appear in scores (Phase 3) and possibly faces (Phase 2 — if face encoding changes).

**Action:** When adding `scores` step, follow same pattern: `SCORE_SCHEMA_VERSION` constant + `score_schema_version` column. Same for faces if anchor algorithm changes.

---

## 10. `init_schema` called from many places

**What:** `init_schema(conn)` is called in `app/api/main.py` (startup), `app/indexer/scan.py`, `app/indexer/google_metadata.py`, `app/indexer/location.py`.

**Why:** Defensive but redundant. Slows startup if anything heavy gets added.

**Action:** Call `init_schema` once at app/CLI entry. Or wrap `get_conn()` to lazy-init on first call (one-shot guard).

---

## 11. `caption.py` per-photo `conn.commit()` inside async tasks

**What:** In `_run_caption_async`, each task does `conn.execute(...)` + `conn.commit()` while sharing one `conn`.

**Why:** `sqlite3.Connection` is not thread-safe across asyncio tasks if the loop uses threads. Also: per-row commit cost adds up.

**Action:** Either:
- Confirm asyncio runs single-thread (it does by default) — then this is safe but slow. Add comment.
- Or use a queue: workers compute results, single writer task drains queue and batches commits every N rows.

Low priority — works today. Revisit if caption throughput becomes a bottleneck.

---

## 12. `tests/__init__.py` empty + no fixtures dir

**What:** Tests work but each file rebuilds DB/fixtures inline.

**Why:** As suite grows, sample photos and stub providers will be repeated.

**Action:** Add `tests/conftest.py` with shared fixtures (`tmp_db`, `stub_caption_provider`, `sample_jpeg_path`).

---

## Not Suggesting

- Switching to Postgres / Elasticsearch — overkill for laptop scale
- Type-checking strictness (mypy/pyright) — fine to defer until after Phase 2
- Renaming `photos-index` CLI — name is clear
- Replacing ChromaDB — works for 100K target
