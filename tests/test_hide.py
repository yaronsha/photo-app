"""Admin-only photo hiding: ADMIN_EMAILS check, hide/unhide endpoints, and
hidden photos left out of search/browse/info for non-admins."""
from __future__ import annotations

import importlib
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.db import Photo, get_session, init_schema
from app.vectordb.base import VectorBackend

from .conftest import make_png

JWT_SECRET = "test-secret-do-not-use-in-prod-min-32-bytes-long"
ADMIN = "admin@example.com"
KID = "kid@example.com"
VISIBLE = "visible000000001"
SECRET = "secret0000000001"


def _hdr(email: str) -> dict:
    token = jwt.encode(
        {"email": email, "sub": "u-" + email, "aud": "authenticated",
         "exp": int(time.time()) + 600},
        JWT_SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _seed(tmp_env) -> None:
    init_schema()
    with get_session() as s:
        for pid, day in ((VISIBLE, "2020-01-01"), (SECRET, "2020-01-02")):
            path = tmp_env["photos_dir"] / f"{pid}.png"
            make_png(path)
            s.add(Photo(
                id=pid,
                storage_path=f"photos/{pid}.png",
                original_filename=f"{pid}.png",
                caption="a photo",
                taken_at=f"{day}T12:00:00+00:00",
                content_type="photo",
            ))


def _client() -> TestClient:
    import app.api.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


@pytest.fixture()
def client(tmp_env, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("ALLOWED_EMAILS", f"{ADMIN},{KID}")
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    _seed(tmp_env)
    return _client()


def _browse_ids(client, email: str) -> set[str]:
    resp = client.get("/search", params={"date_from": "2020-01-01"}, headers=_hdr(email))
    assert resp.status_code == 200
    return {r["id"] for r in resp.json()["results"]}


# ── who may hide ─────────────────────────────────────────────────────────────

def test_non_admin_cannot_hide_or_unhide(client):
    assert client.post(f"/photo/{SECRET}/hide", headers=_hdr(KID)).status_code == 403
    assert client.post(f"/photo/{SECRET}/unhide", headers=_hdr(KID)).status_code == 403
    assert _browse_ids(client, KID) == {VISIBLE, SECRET}


def test_hide_requires_login(client):
    assert client.post(f"/photo/{SECRET}/hide").status_code == 401


def test_empty_admin_list_means_nobody_is_admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "")
    assert client.post(f"/photo/{SECRET}/hide", headers=_hdr(ADMIN)).status_code == 403


def test_me_reports_admin(client):
    assert client.get("/api/me", headers=_hdr(ADMIN)).json()["is_admin"] is True
    assert client.get("/api/me", headers=_hdr(KID)).json()["is_admin"] is False


def test_hide_unknown_photo_404(client):
    assert client.post("/photo/nope/hide", headers=_hdr(ADMIN)).status_code == 404


# ── what hiding does ─────────────────────────────────────────────────────────

def test_admin_hide_removes_photo_for_everyone(client):
    resp = client.post(f"/photo/{SECRET}/hide", headers=_hdr(ADMIN))
    assert resp.status_code == 200
    assert resp.json() == {"id": SECRET, "hidden": True}

    with get_session() as s:
        row = s.get(Photo, SECRET)
        assert row.hidden_at is not None
        assert row.hidden_by == ADMIN

    # Normal search leaves it out for admins too; they use the Hidden view.
    assert _browse_ids(client, KID) == {VISIBLE}
    assert _browse_ids(client, ADMIN) == {VISIBLE}

    # Non-admins get 404 everywhere, as if it didn't exist.
    for path in (f"/photo/{SECRET}/info", f"/photo/{SECRET}", f"/thumb/{SECRET}"):
        assert client.get(path, headers=_hdr(KID), follow_redirects=False).status_code == 404

    # Admins can still open it, flagged as hidden.
    info = client.get(f"/photo/{SECRET}/info", headers=_hdr(ADMIN))
    assert info.status_code == 200
    assert info.json()["hidden"] is True


def test_hidden_view_is_admin_only(client):
    client.post(f"/photo/{SECRET}/hide", headers=_hdr(ADMIN))

    assert client.get("/search", params={"hidden": "only"}, headers=_hdr(KID)).status_code == 403

    resp = client.get("/search", params={"hidden": "only"}, headers=_hdr(ADMIN))
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert [r["id"] for r in results] == [SECRET]
    assert results[0]["hidden"] is True


def test_invalid_hidden_param_400(client):
    resp = client.get("/search", params={"q": "x", "hidden": "all"}, headers=_hdr(ADMIN))
    assert resp.status_code == 400


def test_unhide_restores(client):
    client.post(f"/photo/{SECRET}/hide", headers=_hdr(ADMIN))
    resp = client.post(f"/photo/{SECRET}/unhide", headers=_hdr(ADMIN))
    assert resp.json() == {"id": SECRET, "hidden": False}
    assert _browse_ids(client, KID) == {VISIBLE, SECRET}
    with get_session() as s:
        assert s.get(Photo, SECRET).hidden_by is None


def test_hide_is_idempotent(client):
    client.post(f"/photo/{SECRET}/hide", headers=_hdr(ADMIN))
    with get_session() as s:
        first = s.get(Photo, SECRET).hidden_at
    assert client.post(f"/photo/{SECRET}/hide", headers=_hdr(ADMIN)).status_code == 200
    with get_session() as s:
        assert s.get(Photo, SECRET).hidden_at == first


# ── auth disabled (local dev) ────────────────────────────────────────────────

def test_auth_disabled_everyone_is_admin(tmp_env):
    _seed(tmp_env)
    client = _client()
    assert client.get("/api/me").json()["is_admin"] is True
    assert client.post(f"/photo/{SECRET}/hide").status_code == 200


# ── vector search path ───────────────────────────────────────────────────────

def test_vector_search_excludes_hidden(tmp_env):
    _seed(tmp_env)
    with get_session() as s:
        s.get(Photo, SECRET).hidden_at = "2026-11-18T00:00:00+00:00"

    provider = MagicMock()
    provider.embed.return_value = [0.1] * 1536
    vdb = MagicMock(spec=VectorBackend)
    vdb.count.return_value = 2
    vdb.query.return_value = [(SECRET, 0.1), (VISIBLE, 0.2)]

    import app.search.query as query_mod
    with patch.object(query_mod, "get_embed_provider", return_value=provider):
        results, _ = query_mod.search("anything", vector_db=vdb)
        assert [r.id for r in results] == [VISIBLE]
        results, _ = query_mod.search("anything", vector_db=vdb, hidden="only")
        assert [r.id for r in results] == [SECRET]
