import json
import os
import struct
import zlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.vectordb.base import VectorBackend

# Backend tests don't build the frontend; let app/api/main.py write a stub
# index.html instead of raising at import. Prod has this var unset and so
# fails loud if dist/ is missing.
os.environ.setdefault("FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND", "1")


_png_counter = 0


def make_png(path: Path) -> None:
    """Create a unique 1x1 PNG file (each call has different content)."""
    global _png_counter
    _png_counter += 1

    def chunk(name, data):
        c = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", c)

    r = (_png_counter * 37) % 256
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(bytes([0, r, 255 - r, 128])))
    iend = chunk(b"IEND", b"")
    path.write_bytes(sig + ihdr + idat + iend)


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Isolated photos_dir + data_dir + config.json + OPENAI_API_KEY env."""
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    cfg = {
        "family_name": "Test",
        "data_dir": str(data_dir),
        "photos_dir": str(photos_dir),
        "caption_model": "gpt-4o",
        "embed_model": "text-embedding-3-small",
        "face_tolerance": 0.5,
        "people": [],
        "google_name_aliases": {},
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Don't let an outer DATABASE_URL leak into the test engine.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import app.config as config_mod
    monkeypatch.setattr(config_mod, "_CONFIG_PATH", cfg_path)
    monkeypatch.setattr(config_mod, "_settings", None)

    # Drop any cached SQLAlchemy engine so the next call resolves the new db_path.
    from app.db import dispose_engines
    dispose_engines()

    yield {"photos_dir": photos_dir, "data_dir": data_dir, "cfg_path": cfg_path}

    # Teardown: ensure engines tied to this tmp_path are closed before the
    # directory is wiped (otherwise a stray connection can hold a WAL file).
    dispose_engines()


@pytest.fixture()
def db_session(tmp_env):
    """Yield a session bound to the test's engine."""
    from app.db import get_session, init_schema
    init_schema()
    with get_session() as session:
        yield session


def write_config(cfg_path: Path, **overrides) -> None:
    """Mutate config.json with overrides; clear cached _settings."""
    raw = json.loads(cfg_path.read_text())
    raw.update(overrides)
    cfg_path.write_text(json.dumps(raw))
    import app.config as config_mod
    config_mod._settings = None
    # Settings change → recompute db url; drop cached engine to be safe.
    from app.db import dispose_engines
    dispose_engines()


FULL_CAPTION_RESPONSE = {
    "caption": "A sunny outdoor scene",
    "tags": ["sunny", "outdoor", "nature"],
    "activities": ["walking", "playing"],
    "content_type": "photo",
    "subject_type": "candid_people",
    "primary_focus": "people",
    "indoor_outdoor": "outdoor",
    "setting_type": "park",
    "sharpness": "sharp",
    "face_clarity_score": 3,
}

FAKE_EMBED_VEC = [0.1] * 1536


@pytest.fixture()
def pipeline_env(tmp_env, monkeypatch):
    """tmp_env + pre-wired mock caption/embed providers + mock vector backend."""
    mock_caption_provider = MagicMock()
    mock_caption_provider.caption = AsyncMock(return_value=FULL_CAPTION_RESPONSE)

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed = MagicMock(return_value=FAKE_EMBED_VEC)

    mock_vector_db = MagicMock(spec=VectorBackend)
    mock_vector_db.query.return_value = []
    mock_vector_db.count.return_value = 0
    mock_vector_db.upsert.return_value = None

    return {
        **tmp_env,
        "mock_caption_provider": mock_caption_provider,
        "mock_embed_provider": mock_embed_provider,
        "mock_vector_db": mock_vector_db,
    }
