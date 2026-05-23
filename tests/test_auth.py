"""Tests for app/api/auth.py — JWT verification, allowlist, cron secret.

Auth is opt-in (off when SUPABASE_JWT_SECRET unset) so the existing test
suite stays green. These tests turn it on explicitly per-test by
monkey-patching env + reloading the api module.
"""
from __future__ import annotations

import importlib
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from .conftest import make_png


JWT_SECRET = "test-secret-do-not-use-in-prod-min-32-bytes-long"


def _mint(email: str, *, secret: str = JWT_SECRET, exp: int | None = None,
          aud: str = "authenticated") -> str:
    payload = {
        "email": email,
        "sub": "user-" + email,
        "aud": aud,
        "exp": exp if exp is not None else int(time.time()) + 600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture()
def auth_client(tmp_env, monkeypatch):
    """TestClient with auth enabled (SUPABASE_JWT_SECRET + ALLOWED_EMAILS set)."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("ALLOWED_EMAILS", "ok@example.com,also@example.com")
    import app.api.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


@pytest.fixture()
def cron_client(tmp_env, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "cron-shared-secret")
    import app.api.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


# ── auth disabled (default, rollback path) ───────────────────────────────────

def test_auth_disabled_when_secret_unset(tmp_env):
    """Without SUPABASE_JWT_SECRET, endpoints are open (local-dev mode)."""
    import app.api.main as main_mod
    importlib.reload(main_mod)
    client = TestClient(main_mod.app)
    assert client.get("/people").status_code == 200
    assert client.get("/api/me").status_code == 200


# ── auth enabled, request rejection ──────────────────────────────────────────

def test_missing_token_returns_401(auth_client):
    resp = auth_client.get("/search")
    assert resp.status_code == 401
    assert "bearer" in resp.json()["detail"].lower()


def test_bogus_token_returns_401(auth_client):
    resp = auth_client.get("/search", headers={"Authorization": "Bearer junk"})
    assert resp.status_code == 401


def test_wrong_signature_returns_401(auth_client):
    token = _mint("ok@example.com", secret="different-secret-also-at-least-32-bytes-long")
    resp = auth_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_expired_token_returns_401(auth_client):
    token = _mint("ok@example.com", exp=int(time.time()) - 60)
    resp = auth_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_wrong_audience_returns_401(auth_client):
    token = _mint("ok@example.com", aud="some-other-app")
    resp = auth_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_non_allowlisted_email_returns_403(auth_client):
    token = _mint("stranger@example.com")
    resp = auth_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_allowlist_is_case_insensitive(auth_client):
    token = _mint("OK@Example.com")
    resp = auth_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


# ── auth enabled, request acceptance ─────────────────────────────────────────

def test_valid_token_via_header(auth_client):
    token = _mint("ok@example.com")
    resp = auth_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_valid_token_via_cookie(auth_client):
    token = _mint("ok@example.com")
    resp = auth_client.get("/search", cookies={"sb_jwt": token})
    assert resp.status_code == 200


def test_me_endpoint_returns_claims(auth_client):
    token = _mint("ok@example.com")
    resp = auth_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "ok@example.com"
    assert body["auth_enabled"] is True


# ── presign-redirect for /photo and /thumb ───────────────────────────────────

def _seed_photo(tmp_env, photo_id: str, filename: str = "p.png") -> None:
    photo_path = tmp_env["photos_dir"] / filename
    make_png(photo_path)
    key = str(photo_path.relative_to(tmp_env["data_dir"]))
    from app.db import Photo, get_session, init_schema
    init_schema()
    with get_session() as s:
        s.add(Photo(
            id=photo_id,
            storage_path=key,
            original_filename=filename,
            caption="t",
            taken_at="2020-01-01T00:00:00+00:00",
            content_type="photo",
            scan_indexed_at="2020-01-01T00:00:00+00:00",
        ))


def test_photo_returns_302_to_presign_url(auth_client, tmp_env):
    _seed_photo(tmp_env, "photoredir12345a")
    token = _mint("ok@example.com")
    resp = auth_client.get(
        "/photo/photoredir12345a",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # LocalStorage presigns to /local/<key>; R2Storage signs an HTTPS URL.
    # Either way, the storage path (which ends in the filename) appears in Location.
    assert resp.headers["location"].endswith("photos/p.png")


def test_thumb_returns_302_to_presign_url(auth_client, tmp_env):
    _seed_photo(tmp_env, "thumbredir12345a")
    token = _mint("ok@example.com")
    resp = auth_client.get(
        "/thumb/thumbredir12345a",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("thumbs/thumbredir12345a.jpg")


def test_photo_404_when_storage_key_missing(auth_client, tmp_env):
    """DB row exists but the underlying file does not — should be 404, not a redirect."""
    from app.db import Photo, get_session, init_schema
    init_schema()
    with get_session() as s:
        s.add(Photo(
            id="ghostphoto12345a",
            storage_path="photos/does-not-exist.png",
            original_filename="ghost.png",
            scan_indexed_at="2020-01-01T00:00:00+00:00",
        ))
    token = _mint("ok@example.com")
    resp = auth_client.get(
        "/photo/ghostphoto12345a",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── asymmetric (ES256 / JWKS) path — how real Supabase tokens are signed ─────
#
# Current Supabase projects sign access tokens with ES256 and publish the
# public keys at a JWKS endpoint. We verify against those keys; the shared
# secret is irrelevant on this path. `_signing_key` is monkeypatched to the
# test public key so no network call is made.

_EC_PRIV = ec.generate_private_key(ec.SECP256R1())
_EC_PUB = _EC_PRIV.public_key()
_OTHER_PRIV = ec.generate_private_key(ec.SECP256R1())  # untrusted signer


def _mint_es256(email: str, *, signer=_EC_PRIV, exp: int | None = None,
                aud: str = "authenticated") -> str:
    payload = {
        "email": email,
        "sub": "user-" + email,
        "aud": aud,
        "exp": exp if exp is not None else int(time.time()) + 600,
    }
    return jwt.encode(payload, signer, algorithm="ES256")


@pytest.fixture()
def asym_client(tmp_env, monkeypatch):
    """TestClient with auth enabled via SUPABASE_URL (ES256/JWKS verify)."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv("ALLOWED_EMAILS", "ok@example.com,also@example.com")
    import app.api.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_signing_key", lambda token, jwks_url: _EC_PUB)
    import app.api.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_es256_valid_token_accepted(asym_client):
    token = _mint_es256("ok@example.com")
    resp = asym_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_es256_wrong_signer_rejected(asym_client):
    """Token signed by a key not in the JWKS must fail signature verification."""
    token = _mint_es256("ok@example.com", signer=_OTHER_PRIV)
    resp = asym_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_es256_expired_rejected(asym_client):
    token = _mint_es256("ok@example.com", exp=int(time.time()) - 60)
    resp = asym_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_es256_wrong_audience_rejected(asym_client):
    token = _mint_es256("ok@example.com", aud="some-other-app")
    resp = asym_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_es256_non_allowlisted_email_rejected(asym_client):
    token = _mint_es256("stranger@example.com")
    resp = asym_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_es256_missing_token_rejected(asym_client):
    resp = asym_client.get("/search")
    assert resp.status_code == 401
    assert "bearer" in resp.json()["detail"].lower()


def test_hs256_token_rejected_in_asym_mode(asym_client):
    """No SUPABASE_JWT_SECRET configured → an HS256 token must be refused
    (guards against algorithm-confusion: only the configured trust material
    is honored)."""
    token = _mint("ok@example.com")  # HS256
    resp = asym_client.get("/search", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "alg" in resp.json()["detail"].lower()


def test_es256_me_endpoint(asym_client):
    token = _mint_es256("ok@example.com")
    resp = asym_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "ok@example.com"
    assert body["auth_enabled"] is True


# ── cron endpoint ────────────────────────────────────────────────────────────

def test_cron_dependency_accepts_bearer(cron_client):
    """require_cron is exercised via a dummy route registered on the app."""
    from fastapi import Depends
    import app.api.main as main_mod
    from app.api.auth import require_cron

    @main_mod.app.get("/_test/cron")
    def _cron_probe(_=Depends(require_cron)):
        return {"ok": True}

    resp = cron_client.get(
        "/_test/cron",
        headers={"Authorization": "Bearer cron-shared-secret"},
    )
    assert resp.status_code == 200


def test_cron_dependency_accepts_header(cron_client):
    from fastapi import Depends
    import app.api.main as main_mod
    from app.api.auth import require_cron

    @main_mod.app.get("/_test/cron2")
    def _cron_probe(_=Depends(require_cron)):
        return {"ok": True}

    resp = cron_client.get(
        "/_test/cron2",
        headers={"X-Cron-Secret": "cron-shared-secret"},
    )
    assert resp.status_code == 200


def test_cron_dependency_rejects_bad_secret(cron_client):
    from fastapi import Depends
    import app.api.main as main_mod
    from app.api.auth import require_cron

    @main_mod.app.get("/_test/cron3")
    def _cron_probe(_=Depends(require_cron)):
        return {"ok": True}

    resp = cron_client.get(
        "/_test/cron3",
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 403


def test_cron_dependency_rejects_missing(cron_client):
    from fastapi import Depends
    import app.api.main as main_mod
    from app.api.auth import require_cron

    @main_mod.app.get("/_test/cron4")
    def _cron_probe(_=Depends(require_cron)):
        return {"ok": True}

    resp = cron_client.get("/_test/cron4")
    assert resp.status_code == 403
