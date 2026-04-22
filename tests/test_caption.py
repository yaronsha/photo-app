import json
import sqlite3
import struct
import zlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_caption_mocked_provider(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    img = photos_dir / "photo.png"
    _make_png(img)

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value={
        "caption": "A sunny beach scene",
        "tags": ["beach", "sunny", "ocean"],
    })

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=50)

    assert count == 1
    mock_provider.caption.assert_called_once()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT caption, tags FROM photos").fetchone()
    assert row["caption"] == "A sunny beach scene"
    assert json.loads(row["tags"]) == ["beach", "sunny", "ocean"]
    conn.close()


def test_caption_skips_already_captioned(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "photo.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value={"caption": "First caption", "tags": []})

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=50)

    mock_provider.caption.reset_mock()

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=50)

    mock_provider.caption.assert_not_called()


def test_caption_limit_respected(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    for i in range(5):
        _make_png(photos_dir / f"photo_{i}.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value={"caption": "A photo", "tags": []})

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=3)

    assert count == 3
    assert mock_provider.caption.call_count == 3
