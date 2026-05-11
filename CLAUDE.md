# Agent Instructions — Family Photos AI App

Read [README.md](README.md)
Architecture and pipeline detail live in [docs/](docs/) — read the relevant doc when working in that area.

## Doc Map

| Working on… | Read |
|---|---|
| Indexer steps, schema | [docs/INDEXING.md](docs/INDEXING.md) + [app/indexer/CLAUDE.md](app/indexer/CLAUDE.md) |
| Search/query | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API endpoints | [docs/API.md](docs/API.md) |
| Setup, commands, tests | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| Faces | [FACE_RECOGNITION.md](FACE_RECOGNITION.md) |
| Future work | [docs/ROADMAP.md](docs/ROADMAP.md) |

## Planning Discipline

- When asked to create a plan, keep it high-level (goals, phases, deliverables) — do NOT include implementation details (function signatures, code snippets, file-level internals) unless explicitly requested.
- Put deep technical content in `docs/` — not in this file or top-level.

## Documentation Discipline

Keep docs aligned with code — but only when a change actually affects something the docs describe. Most commits don't need doc updates.

**Update docs when** a change adds/removes/alters documented behavior:

| Change | Update |
|---|---|
| Indexer step added, removed, or behavior-changed | [docs/INDEXING.md](docs/INDEXING.md) + [app/indexer/CLAUDE.md](app/indexer/CLAUDE.md) |
| API endpoint, param, or response shape changed | [docs/API.md](docs/API.md) |
| Schema column / table added or removed | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) schema section |
| New CLI command, flag, env var, or config field | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| Phase milestone shipped or roadmap shifts | [docs/ROADMAP.md](docs/ROADMAP.md) |

**Skip docs for:** internal refactors (no behavior change), typo fixes, dependency bumps, test-only changes, in-progress WIP commits.

If docs and code disagree, code is truth — fix the doc in the same commit.

## Verification Before Action

- Before any multi-step job (embed, caption, batch test), confirm plan with user and verify logging first.
- When analyzing screenshots or multi-file evidence, review ALL items before summarizing — do not generalize from one sample.
- Do NOT verify external APIs (e.g. Google Photos API) from memory — link to current docs.

## Autonomous Action Limits

- Do NOT add score thresholds, delete methods during refactors, or change search/embedding behavior without explicit approval.
- Keep SQLite transactions short in embed/caption pipelines — avoid lock contention (caption is async w/ semaphore, embed is sync).
- When user asks "which?" or a clarifying question, re-list the items — do not deflect.

## Communication Style

- When user describes a goal, propose 2-3 concrete options with tradeoffs BEFORE asking clarifying questions.
- Suggest, don't just ask.

## Hard Rules — Do Not

- Do not use ChromaDB `collection.add()` — always `upsert()`
- Do not run `--step caption` on all photos without `--limit` first (API costs money)
- Do not store face images or embeddings in ChromaDB — SQLite only
- Do not add cloud face recognition (AWS Rekognition etc.) — privacy constraint
- Do not mix game logic into search or indexing layers
- Do not commit design specs to git in this project (per user preference)

## Project Summary

Local-first family photo search + games app. Python + FastAPI + SQLite + ChromaDB + face_recognition. ~100K photos / 200GB. Personal project, forkable per family.

## Architecture Rules (one-liners)

- Search and display are decoupled. Search returns `photo[]`. Display logic never inside search.
- Games = query plugins on existing index. No new indexing per game type.
- Scores live in SQLite columns, not vector DB.
- ChromaDB = semantic similarity only. Filtering/sorting = SQLite. Join on `photo_id`.
- ChromaDB metadata is minimal — only fields needed for pre-filter (`year`).

For full architectural reasoning see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
