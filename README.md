# Family Photos AI App

[![tests](https://github.com/yaronsha/photo-app/actions/workflows/tests.yml/badge.svg)](https://github.com/yaronsha/photo-app/actions/workflows/tests.yml)

Local-first web app to search, browse, and play with a family photo collection using AI.

Runs entirely on a laptop. No cloud at runtime. API calls only at index time (captions + embeddings).

## What It Does

- **Natural language search** — "grandma at the beach", "rainy trip to Rome", "kids eating cake"
- **Person search** — filter by named family member (any/all)
- **Date filtering** — year, month, day range
- **Games** _(planned)_ — "who is this?", "guess the year", baby match, odd one out
- **Lightbox viewer** — caption, location, people, tags, original Google Photos note

## Quick Start

```bash
# 1. Install deps
uv sync

# 2. Configure
cp .env.example .env                       # add OPENAI_API_KEY
$EDITOR config.json                        # set family_name, people, aliases

# 3. Import photos (Google Takeout)
uv run photos-index --step merge --folders ~/Downloads/Takeout/Google\ Photos
uv run photos-index --step google_metadata
uv run photos-index --step location
uv run photos-index --step caption --limit 50    # test small batch first
uv run photos-index --step embed

# 4. Run web UI
uv run uvicorn app.api.main:app --reload --port 8000
# open http://localhost:8000
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for full setup and command reference.

## Documentation

| File | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Stack, layers, data flow, SQLite + ChromaDB schema |
| [docs/INDEXING.md](docs/INDEXING.md) | Pipeline steps, idempotency, schema versioning |
| [docs/API.md](docs/API.md) | FastAPI endpoint reference |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Env setup, common tasks, testing |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phase 2 (faces) + Phase 3 (games, scores) |
| [docs/REFACTOR_SUGGESTIONS.md](docs/REFACTOR_SUGGESTIONS.md) | Proposed code restructures |
| [FACE_RECOGNITION.md](FACE_RECOGNITION.md) | Anchor-based face matching design |
| [CLAUDE.md](CLAUDE.md) | Agent collaboration rules |

## Project Constraints

- **Local only** — no cloud at runtime. Privacy-first (face data stays on device).
- **Forkable per family** — one `data/` folder per family, shared app code.
- **Idempotent indexing** — every step safe to re-run.
- **Scale target** — ~100K photos / 200GB on a single laptop.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+ · FastAPI · uvicorn |
| Metadata | SQLite (WAL mode) |
| Vectors | ChromaDB (local persistent) |
| Vision LLM | OpenAI `gpt-4.1-nano` (Phase 1 default) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Faces _(Phase 2)_ | `face_recognition` (dlib, local) |
| Frontend | Vanilla HTML / JS / CSS |
| Env | `uv` + `pyproject.toml` |

## Layout

```
family-photos-app/
├── app/                  shared code (indexer, search, api, web)
├── config.json           per-family config (people, aliases, model names)
├── data/                 SQLite, ChromaDB, sidecars, thumbs (gitignored)
├── photos/               photo collection (gitignored)
├── docs/                 architecture + development docs
├── tests/                pytest suite
├── pyproject.toml        deps + scripts entry
├── README.md             this file
├── CLAUDE.md             agent rules
└── FACE_RECOGNITION.md   face design notes
```
