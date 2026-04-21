import json
import sqlite3
import struct
import zlib
from pathlib import Path
from unittest.mock import patch

import pytest


_png_counter = 0


def _make_png(path: Path) -> None:
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
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.config as config_mod
    monkeypatch.setattr(config_mod, "_CONFIG_PATH", cfg_path)
    monkeypatch.setattr(config_mod, "_settings", None)

    return {"photos_dir": photos_dir, "data_dir": data_dir}


def test_scan_indexes_png(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "test.png")

    import app.db as db_mod
    import app.indexer.scan as scan_mod

    with patch.object(db_mod, "get_conn", wraps=db_mod.get_conn):
        scan_mod.run_scan()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM photos").fetchall()
    assert len(rows) == 1
    assert rows[0]["original_filename"] == "test.png"
    assert rows[0]["scan_indexed_at"] is not None
    conn.close()


def test_scan_idempotent(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "a.png")
    _make_png(photos_dir / "b.png")

    import app.indexer.scan as scan_mod

    scan_mod.run_scan()
    scan_mod.run_scan()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    rows = conn.execute("SELECT * FROM photos").fetchall()
    assert len(rows) == 2
    conn.close()


def test_scan_dedup_by_content(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    img_bytes_path = photos_dir / "orig.png"
    _make_png(img_bytes_path)
    copy_path = photos_dir / "copy.png"
    copy_path.write_bytes(img_bytes_path.read_bytes())

    import app.indexer.scan as scan_mod

    scan_mod.run_scan()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    rows = conn.execute("SELECT * FROM photos").fetchall()
    assert len(rows) == 1
    conn.close()
