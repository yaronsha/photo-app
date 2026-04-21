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

    return {"data_dir": data_dir, "photos_dir": photos_dir}


def _seed_db(data_dir: Path, photos_dir: Path) -> str:
    db_path = data_dir / "photos.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY, storage_path TEXT NOT NULL UNIQUE,
            original_filename TEXT NOT NULL, taken_at TIMESTAMP,
            location_name TEXT, lat REAL, lng REAL,
            caption TEXT, tags TEXT,
            happiness_score REAL, aesthetic_score REAL,
            scan_indexed_at TIMESTAMP, caption_indexed_at TIMESTAMP,
            vector_indexed_at TIMESTAMP, face_indexed_at TIMESTAMP
        )
    """)
    photo_path = str(photos_dir / "beach.jpg")
    conn.execute(
        "INSERT INTO photos (id, storage_path, original_filename, caption, tags, "
        "taken_at, scan_indexed_at, caption_indexed_at, vector_indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "abc123def456abc1",
            photo_path,
            "beach.jpg",
            "A sunny day at the beach",
            json.dumps(["beach", "sunny", "ocean"]),
            "2022-07-15T12:00:00+00:00",
            "2022-07-15T12:00:00+00:00",
            "2022-07-15T12:00:00+00:00",
            "2022-07-15T12:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()
    return "abc123def456abc1"


def test_search_returns_results(tmp_env):
    data_dir = tmp_env["data_dir"]
    photos_dir = tmp_env["photos_dir"]
    photo_id = _seed_db(data_dir, photos_dir)

    mock_embed_provider = MagicMock()
    query_vec = [0.1] * 1536
    mock_embed_provider.embed.return_value = query_vec

    mock_collection = MagicMock()
    mock_collection.count.return_value = 1
    mock_collection.query.return_value = {
        "ids": [[photo_id]],
        "distances": [[0.1]],
    }

    import app.search.query as query_mod

    with (
        patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider),
        patch.object(query_mod, "get_collection", return_value=mock_collection),
    ):
        results = query_mod.search("beach", limit=10)

    assert len(results) == 1
    assert results[0].id == photo_id
    assert results[0].caption == "A sunny day at the beach"
    assert abs(results[0].score - 0.9) < 0.001


def test_search_empty_collection(tmp_env):
    _seed_db(tmp_env["data_dir"], tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed.return_value = [0.0] * 1536

    mock_collection = MagicMock()
    mock_collection.count.return_value = 0
    mock_collection.query.return_value = {"ids": [[]], "distances": [[]]}

    import app.search.query as query_mod

    with (
        patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider),
        patch.object(query_mod, "get_collection", return_value=mock_collection),
    ):
        results = query_mod.search("anything")

    assert results == []
