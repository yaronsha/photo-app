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


_FULL_RESPONSE = {
    "caption": "A sunny beach scene",
    "tags": ["beach", "sunny", "ocean"],
    "activities": ["swimming", "playing"],
    "content_type": "photo",
    "subject_type": "candid_people",
    "primary_focus": "people",
    "indoor_outdoor": "outdoor",
    "setting_type": "beach",
    "sharpness": "sharp",
    "face_clarity_score": 4,
}


def _minimal_response(**overrides):
    out = dict(_FULL_RESPONSE)
    out.update(overrides)
    return out


def test_caption_mocked_provider(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    img = photos_dir / "photo.png"
    _make_png(img)

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=50)

    assert count == 1
    mock_provider.caption.assert_called_once()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT caption, tags, activities, content_type, subject_type, "
        "primary_focus, indoor_outdoor, setting_type, sharpness, "
        "face_clarity_score, caption_schema_version FROM photos"
    ).fetchone()
    assert row["caption"] == "A sunny beach scene"
    assert json.loads(row["tags"]) == ["beach", "sunny", "ocean"]
    assert json.loads(row["activities"]) == ["swimming", "playing"]
    assert row["content_type"] == "photo"
    assert row["subject_type"] == "candid_people"
    assert row["primary_focus"] == "people"
    assert row["indoor_outdoor"] == "outdoor"
    assert row["setting_type"] == "beach"
    assert row["sharpness"] == "sharp"
    assert row["face_clarity_score"] == 4
    assert row["caption_schema_version"] == caption_mod.CAPTION_SCHEMA_VERSION
    conn.close()


def test_caption_face_clarity_null_when_no_faces(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "photo.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(
        return_value=_minimal_response(
            subject_type="landscape",
            primary_focus="place",
            face_clarity_score=None,
        )
    )

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=1)

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT face_clarity_score FROM photos").fetchone()
    assert row["face_clarity_score"] is None
    conn.close()


def test_caption_skips_already_captioned(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "photo.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=50)

    mock_provider.caption.reset_mock()

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=50)

    mock_provider.caption.assert_not_called()


def test_caption_picks_up_stale_schema_version(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "photo.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    db_path = tmp_env["data_dir"] / "photos.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE photos SET caption='old', caption_indexed_at='2020-01-01T00:00:00', "
        "caption_schema_version=1"
    )
    conn.commit()
    conn.close()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=10)

    assert count == 1
    mock_provider.caption.assert_called_once()


def test_caption_limit_respected(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    for i in range(5):
        _make_png(photos_dir / f"photo_{i}.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=3)

    assert count == 3
    assert mock_provider.caption.call_count == 3
