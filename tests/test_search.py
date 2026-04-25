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


def _create_schema(conn):
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, family_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS photo_people (
            photo_id TEXT NOT NULL, person_id TEXT NOT NULL,
            face_bbox TEXT, confidence REAL,
            PRIMARY KEY (photo_id, person_id)
        )
    """)


def _seed_db(data_dir: Path, photos_dir: Path) -> str:
    db_path = data_dir / "photos.db"
    conn = sqlite3.connect(str(db_path))
    _create_schema(conn)
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


def _seed_multi(data_dir: Path, photos_dir: Path) -> list[str]:
    db_path = data_dir / "photos.db"
    conn = sqlite3.connect(str(db_path))
    _create_schema(conn)
    rows = [
        ("id_feb2015", "feb15.jpg", "2015-02-10T12:00:00+00:00", "feb 2015"),
        ("id_mar2015", "mar15.jpg", "2015-03-15T12:00:00+00:00", "mar 2015"),
        ("id_mar2015b", "mar15b.jpg", "2015-03-28T12:00:00+00:00", "mar 2015 late"),
        ("id_apr2015", "apr15.jpg", "2015-04-05T12:00:00+00:00", "apr 2015"),
    ]
    for pid, fname, taken, cap in rows:
        conn.execute(
            "INSERT INTO photos (id, storage_path, original_filename, caption, "
            "taken_at, scan_indexed_at, caption_indexed_at, vector_indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, str(photos_dir / fname), fname, cap, taken, taken, taken, taken),
        )
    conn.commit()
    conn.close()
    return [r[0] for r in rows]


def test_browse_by_date_range_no_query(tmp_env):
    ids = _seed_multi(tmp_env["data_dir"], tmp_env["photos_dir"])

    import app.search.query as query_mod

    mock_collection = MagicMock()
    mock_embed_provider = MagicMock()

    with (
        patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider),
        patch.object(query_mod, "get_collection", return_value=mock_collection),
    ):
        results = query_mod.search(
            None, date_from="2015-03-01", date_to="2015-03-31"
        )

    result_ids = {r.id for r in results}
    assert result_ids == {"id_mar2015", "id_mar2015b"}
    assert results[0].taken_at > results[1].taken_at  # DESC
    mock_collection.query.assert_not_called()
    mock_embed_provider.embed.assert_not_called()


def test_browse_empty_returns_nothing(tmp_env):
    _seed_multi(tmp_env["data_dir"], tmp_env["photos_dir"])

    import app.search.query as query_mod

    assert query_mod.search(None) == []
    assert query_mod.search("") == []


def test_vector_search_filters_by_date(tmp_env):
    ids = _seed_multi(tmp_env["data_dir"], tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed.return_value = [0.1] * 1536

    mock_collection = MagicMock()
    mock_collection.count.return_value = 4
    mock_collection.query.return_value = {
        "ids": [ids],
        "distances": [[0.1, 0.2, 0.3, 0.4]],
    }

    import app.search.query as query_mod

    with (
        patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider),
        patch.object(query_mod, "get_collection", return_value=mock_collection),
    ):
        results = query_mod.search(
            "anything", date_from="2015-03-01", date_to="2015-03-31"
        )

    assert {r.id for r in results} == {"id_mar2015", "id_mar2015b"}


def test_date_to_inclusive(tmp_env):
    _seed_multi(tmp_env["data_dir"], tmp_env["photos_dir"])

    import app.search.query as query_mod

    with (
        patch.object(query_mod, "get_embed_provider", return_value=MagicMock()),
        patch.object(query_mod, "get_collection", return_value=MagicMock()),
    ):
        # date_to inclusive — 2015-03-28 should include the 2015-03-28T12:00 photo
        results = query_mod.search(
            None, date_from="2015-03-28", date_to="2015-03-28"
        )

    assert {r.id for r in results} == {"id_mar2015b"}


def _seed_people_db(data_dir: Path, photos_dir: Path) -> dict:
    """3 photos: photo_ab (alice+bob), photo_a (alice only), photo_b (bob only)."""
    db_path = data_dir / "photos.db"
    conn = sqlite3.connect(str(db_path))
    _create_schema(conn)
    for pid, fname, taken in [
        ("photo_ab", "ab.jpg", "2020-01-01T12:00:00+00:00"),
        ("photo_a",  "a.jpg",  "2020-01-02T12:00:00+00:00"),
        ("photo_b",  "b.jpg",  "2020-01-03T12:00:00+00:00"),
    ]:
        conn.execute(
            "INSERT INTO photos (id, storage_path, original_filename, caption, "
            "taken_at, scan_indexed_at, caption_indexed_at, vector_indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, str(photos_dir / fname), fname, "caption", taken, taken, taken, taken),
        )
    conn.execute("INSERT INTO people VALUES ('alice', 'Alice', NULL)")
    conn.execute("INSERT INTO people VALUES ('bob',   'Bob',   NULL)")
    for photo_id, person_id in [
        ("photo_ab", "alice"), ("photo_ab", "bob"),
        ("photo_a",  "alice"),
        ("photo_b",  "bob"),
    ]:
        conn.execute(
            "INSERT INTO photo_people (photo_id, person_id) VALUES (?, ?)",
            (photo_id, person_id),
        )
    conn.commit()
    conn.close()
    return {"photo_ab": "photo_ab", "photo_a": "photo_a", "photo_b": "photo_b"}


def test_browse_people_any_mode(tmp_env):
    _seed_people_db(tmp_env["data_dir"], tmp_env["photos_dir"])

    import app.search.query as query_mod

    with (
        patch.object(query_mod, "get_embed_provider", return_value=MagicMock()),
        patch.object(query_mod, "get_collection", return_value=MagicMock()),
    ):
        results = query_mod.search(
            None,
            date_from="2020-01-01",
            date_to="2020-01-03",
            person_ids=["alice", "bob"],
            people_mode="any",
        )

    assert {r.id for r in results} == {"photo_ab", "photo_a", "photo_b"}


def test_browse_people_all_mode(tmp_env):
    _seed_people_db(tmp_env["data_dir"], tmp_env["photos_dir"])

    import app.search.query as query_mod

    with (
        patch.object(query_mod, "get_embed_provider", return_value=MagicMock()),
        patch.object(query_mod, "get_collection", return_value=MagicMock()),
    ):
        results = query_mod.search(
            None,
            date_from="2020-01-01",
            date_to="2020-01-03",
            person_ids=["alice", "bob"],
            people_mode="all",
        )

    assert {r.id for r in results} == {"photo_ab"}


def test_vector_search_people_all_mode(tmp_env):
    _seed_people_db(tmp_env["data_dir"], tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed.return_value = [0.1] * 1536

    mock_collection = MagicMock()
    mock_collection.count.return_value = 3
    mock_collection.query.return_value = {
        "ids": [["photo_ab", "photo_a", "photo_b"]],
        "distances": [[0.1, 0.2, 0.3]],
    }

    import app.search.query as query_mod

    with (
        patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider),
        patch.object(query_mod, "get_collection", return_value=mock_collection),
    ):
        results = query_mod.search(
            "family",
            person_ids=["alice", "bob"],
            people_mode="all",
        )

    assert {r.id for r in results} == {"photo_ab"}
