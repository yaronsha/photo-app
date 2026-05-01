import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()

    cfg = {
        "family_name": "Test",
        "data_dir": str(data_dir),
        "photos_dir": str(photos_dir),
        "caption_model": "gpt-4.1-nano",
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

    return {"data_dir": data_dir, "photos_dir": photos_dir}


def _seed(db_path: Path, rows: list[tuple]):
    conn = sqlite3.connect(str(db_path))
    from app.db import init_schema
    init_schema(conn)
    for pid, caption, activities, content_type in rows:
        conn.execute(
            "INSERT INTO photos (id, storage_path, original_filename, caption, "
            "activities, content_type, taken_at, scan_indexed_at, caption_indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pid, f"/tmp/{pid}.jpg", f"{pid}.jpg",
                caption, json.dumps(activities), content_type,
                "2022-01-01T00:00:00+00:00",
                "2022-01-01T00:00:00+00:00",
                "2022-01-01T00:00:00+00:00",
            ),
        )
    conn.commit()
    conn.close()


def test_embed_skips_documents(tmp_env):
    db_path = tmp_env["data_dir"] / "photos.db"
    _seed(db_path, [
        ("p_photo", "a beach", ["swimming"], "photo"),
        ("p_doc", "a receipt", [], "document"),
        ("p_other", "a meme", [], "other"),
    ])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536

    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        count = embed_mod.run_embed()

    assert count == 1
    upsert_calls = mock_collection.upsert.call_args_list
    upserted_ids = [call.kwargs["ids"][0] for call in upsert_calls]
    assert upserted_ids == ["p_photo"]


def test_embed_text_includes_activities(tmp_env):
    db_path = tmp_env["data_dir"] / "photos.db"
    _seed(db_path, [
        ("p1", "kids on beach", ["swimming", "playing"], "photo"),
    ])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536

    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        embed_mod.run_embed()

    assert mock_provider.embed.call_count == 1
    text = mock_provider.embed.call_args.args[0]
    assert "kids on beach" in text
    assert "swimming" in text
    assert "playing" in text


def test_embed_text_omits_tags(tmp_env):
    """Tags column should NOT be part of embed text — only caption + activities."""
    db_path = tmp_env["data_dir"] / "photos.db"
    conn = sqlite3.connect(str(db_path))
    from app.db import init_schema
    init_schema(conn)
    conn.execute(
        "INSERT INTO photos (id, storage_path, original_filename, caption, tags, "
        "activities, content_type, taken_at, scan_indexed_at, caption_indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "p1", "/tmp/p1.jpg", "p1.jpg",
            "two children running",
            json.dumps(["zebrazebra", "yellowbananatag", "purpleorchid"]),
            json.dumps([]),
            "photo",
            "2022-01-01T00:00:00+00:00",
            "2022-01-01T00:00:00+00:00",
            "2022-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536
    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        embed_mod.run_embed()

    text = mock_provider.embed.call_args.args[0]
    assert "two children running" in text
    for tag in ("zebrazebra", "yellowbananatag", "purpleorchid"):
        assert tag not in text, f"tag {tag!r} should not be in embed text"
