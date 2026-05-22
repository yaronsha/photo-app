"""Tests for app/api/main.py — FastAPI endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .conftest import make_png, write_config


def _seed_photo(tmp_env, photo_id: str = "abc123def456abc1", filename: str = "test.png",
                taken_at: str = "2020-01-01T12:00:00+00:00",
                content_type: str = "photo") -> Path:
    """Create photo file + DB row + initialized schema. Returns path to file."""
    photo_path = tmp_env["photos_dir"] / filename
    make_png(photo_path)

    # storage_path is a key relative to data_dir (LocalStorage root).
    data_dir = tmp_env["data_dir"]
    key = str(photo_path.relative_to(data_dir))

    from app.db import Photo, get_session, init_schema
    init_schema()
    with get_session() as s:
        s.add(Photo(
            id=photo_id,
            storage_path=key,
            original_filename=filename,
            caption="a test photo",
            taken_at=taken_at,
            content_type=content_type,
            scan_indexed_at=taken_at,
            caption_indexed_at=taken_at,
            vector_indexed_at=taken_at,
        ))
    return photo_path


@pytest.fixture()
def client(tmp_env):
    """Fresh FastAPI TestClient per test (avoids module-level state across tests)."""
    import importlib
    import app.api.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_people_endpoint(tmp_env, client):
    write_config(tmp_env["cfg_path"], people=[
        {"id": "yaron", "name": "Yaron Shapira"},
        {"id": "noa", "name": "Noa Shapira"},
    ])
    # Recreate client so it picks up the new config
    import importlib
    import app.api.main as main_mod
    importlib.reload(main_mod)
    fresh = TestClient(main_mod.app)

    resp = fresh.get("/people")
    assert resp.status_code == 200
    data = resp.json()
    assert {p["id"] for p in data} == {"yaron", "noa"}


def test_search_invalid_date_returns_400(client):
    resp = client.get("/search", params={"q": "x", "date_from": "not-a-date"})
    assert resp.status_code == 400
    assert "date_from" in resp.json()["detail"]


def test_search_invalid_people_mode_returns_400(client):
    resp = client.get("/search", params={"q": "x", "people_mode": "bogus"})
    assert resp.status_code == 400


def test_search_empty_query_no_filters_returns_empty(client):
    resp = client.get("/search")
    assert resp.status_code == 200
    assert resp.json() == {"results": [], "has_more": False}


def test_search_browse_mode_returns_results(tmp_env, client):
    _seed_photo(tmp_env)

    resp = client.get("/search", params={"date_from": "2020-01-01", "date_to": "2020-01-01"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["caption"] == "a test photo"
    assert results[0]["thumb_url"].startswith("/thumb/")


def test_photo_info_endpoint(tmp_env, client):
    _seed_photo(tmp_env, photo_id="abc123def456abc1")

    resp = client.get("/photo/abc123def456abc1/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "abc123def456abc1"
    assert body["caption"] == "a test photo"
    assert body["people"] == []


def test_photo_info_404_for_unknown_id(tmp_env, client):
    from app.db import init_schema
    init_schema()

    resp = client.get("/photo/nonexistent/info")
    assert resp.status_code == 404


def test_photo_bad_key_prefix_rejected(tmp_env, client):
    """A row whose storage_path key does not start with 'photos/' should 403."""
    from app.db import Photo, get_session, init_schema
    init_schema()
    with get_session() as s:
        s.add(Photo(
            id="evilid000000abcd",
            storage_path="../../../etc/passwd",  # not under photos/ prefix
            original_filename="outside",
            scan_indexed_at="2020-01-01T00:00:00+00:00",
        ))

    resp = client.get("/photo/evilid000000abcd", follow_redirects=False)
    assert resp.status_code == 403


def test_photo_traversal_segment_rejected(tmp_env, client):
    """A key containing a '..' path segment should 403 even with photos/ prefix."""
    from app.db import Photo, get_session, init_schema
    init_schema()
    with get_session() as s:
        s.add(Photo(
            id="trav123456abcdef",
            storage_path="photos/../../etc/passwd",
            original_filename="trav",
            scan_indexed_at="2020-01-01T00:00:00+00:00",
        ))

    resp = client.get("/photo/trav123456abcdef", follow_redirects=False)
    assert resp.status_code == 403


def test_photo_404_when_row_missing(client):
    from app.db import init_schema
    init_schema()

    resp = client.get("/photo/nonexistent", follow_redirects=False)
    assert resp.status_code == 404


def test_thumb_generates_and_caches(tmp_env, client):
    _seed_photo(tmp_env, photo_id="thumbtest1234567")

    resp = client.get("/thumb/thumbtest1234567", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("thumbs/thumbtest1234567.jpg")

    cached = tmp_env["data_dir"] / "thumbs" / "thumbtest1234567.jpg"
    assert cached.exists()


def test_thumb_uses_cache_on_second_request(tmp_env, client):
    _seed_photo(tmp_env, photo_id="cachetest1234567")

    # First request — generates
    client.get("/thumb/cachetest1234567", follow_redirects=False)
    cached = tmp_env["data_dir"] / "thumbs" / "cachetest1234567.jpg"
    first_mtime = cached.stat().st_mtime

    # Second request — should use cache, not re-generate
    client.get("/thumb/cachetest1234567", follow_redirects=False)
    assert cached.stat().st_mtime == first_mtime


def test_search_excludes_documents_by_default(tmp_env, client):
    _seed_photo(tmp_env, photo_id="photo000000000ab", filename="p.png", content_type="photo")
    _seed_photo(tmp_env, photo_id="docid00000000cd", filename="d.png", content_type="document")

    resp = client.get("/search", params={"date_from": "2020-01-01", "date_to": "2020-01-01"})
    ids = {r["id"] for r in resp.json()["results"]}
    assert ids == {"photo000000000ab"}


def test_search_include_docs_returns_documents(tmp_env, client):
    _seed_photo(tmp_env, photo_id="photo000000000ab", filename="p.png", content_type="photo")
    _seed_photo(tmp_env, photo_id="docid00000000cd", filename="d.png", content_type="document")

    resp = client.get(
        "/search",
        params={"date_from": "2020-01-01", "date_to": "2020-01-01", "include_docs": "true"},
    )
    ids = {r["id"] for r in resp.json()["results"]}
    assert ids == {"photo000000000ab", "docid00000000cd"}


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
