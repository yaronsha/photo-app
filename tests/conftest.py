import json
import struct
import zlib
from pathlib import Path

import pytest


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

    import app.config as config_mod
    monkeypatch.setattr(config_mod, "_CONFIG_PATH", cfg_path)
    monkeypatch.setattr(config_mod, "_settings", None)

    return {"photos_dir": photos_dir, "data_dir": data_dir, "cfg_path": cfg_path}


def write_config(cfg_path: Path, **overrides) -> None:
    """Mutate config.json with overrides; clear cached _settings."""
    raw = json.loads(cfg_path.read_text())
    raw.update(overrides)
    cfg_path.write_text(json.dumps(raw))
    import app.config as config_mod
    config_mod._settings = None
