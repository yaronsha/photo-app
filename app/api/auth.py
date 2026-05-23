"""JWT verification + email allowlist for Supabase-issued tokens.

Auth is **opt-in**: if neither `SUPABASE_URL`/`SUPABASE_JWKS_URL` nor
`SUPABASE_JWT_SECRET` is set, `require_auth` is a no-op. This preserves the
"run locally with env vars only" rollback path (see
docs/migration/README.md "Critical invariant").

Supabase signs access tokens with **asymmetric keys (ES256/RS256)** by
default on current projects, fetched from the project's JWKS endpoint.
Older / migrated projects may still use the **HS256 shared secret**. We
support both, but pick the verifier strictly from configured trust
material so the two paths never blur into an algorithm-confusion hole:

  - `SUPABASE_URL` (or explicit `SUPABASE_JWKS_URL`) set  → ES256/RS256
    verified against JWKS public keys.
  - `SUPABASE_JWT_SECRET` set                              → HS256 verified
    against the shared secret.

If both are set, the token's `alg` header selects the path (each path has
independent trust material, so this is safe). The `email` claim must be in
`ALLOWED_EMAILS` (comma-separated env list).

Cron endpoints use `require_cron` instead — shared bearer in
`Authorization` header or `X-Cron-Secret`, compared to `CRON_SECRET`.
"""
from __future__ import annotations

import hmac
import os

import jwt
from fastapi import HTTPException, Request

_ASYM_ALGS = ("ES256", "RS256")

# PyJWKClient caches keys internally; reuse one client per JWKS URL so we
# don't re-fetch the key set on every request.
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_url() -> str | None:
    """JWKS endpoint, from explicit override or derived from SUPABASE_URL.

    Derived only from a *configured* base URL — never from the token's own
    `iss` claim — so an attacker can't point verification at a JWKS they
    control.
    """
    explicit = os.environ.get("SUPABASE_JWKS_URL")
    if explicit:
        return explicit
    base = os.environ.get("SUPABASE_URL")
    if base:
        return base.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    return None


def _auth_enabled() -> bool:
    return bool(_jwks_url() or os.environ.get("SUPABASE_JWT_SECRET"))


def _allowed_emails() -> set[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("sb_jwt")


def _signing_key(token: str, jwks_url: str):
    """Resolve the asymmetric public key for `token` from the JWKS endpoint.

    Split out so tests can monkeypatch it with a local key and avoid a
    network call.
    """
    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url)
        _jwks_clients[jwks_url] = client
    return client.get_signing_key_from_jwt(token).key


def _decode(token: str) -> dict:
    """Verify `token` and return its claims, or raise jwt.PyJWTError."""
    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except jwt.PyJWTError:
        raise jwt.InvalidTokenError("malformed token header")

    jwks_url = _jwks_url()
    secret = os.environ.get("SUPABASE_JWT_SECRET")

    if alg in _ASYM_ALGS and jwks_url:
        key = _signing_key(token, jwks_url)
        return jwt.decode(token, key, algorithms=list(_ASYM_ALGS), audience="authenticated")
    if alg == "HS256" and secret:
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")

    raise jwt.InvalidAlgorithmError(f"The specified alg value is not allowed: {alg}")


def require_auth(request: Request) -> dict:
    """FastAPI dependency. Returns decoded claims (or `{}` if auth disabled)."""
    if not _auth_enabled():
        return {}

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    try:
        claims = _decode(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.PyJWKClientError as exc:
        raise HTTPException(status_code=401, detail=f"could not fetch signing key: {exc}")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}")

    allowed = _allowed_emails()
    email = (claims.get("email") or "").lower()
    if allowed and email not in allowed:
        raise HTTPException(status_code=403, detail="email not allowed")

    return claims


def require_cron(request: Request) -> None:
    """FastAPI dependency for cron endpoints. Bypassed if `CRON_SECRET` unset."""
    expected = os.environ.get("CRON_SECRET")
    if not expected:
        return

    bearer = request.headers.get("Authorization", "")
    bearer_tok = bearer[7:] if bearer.startswith("Bearer ") else ""
    header_tok = request.headers.get("X-Cron-Secret", "")

    if not (
        hmac.compare_digest(bearer_tok, expected)
        or hmac.compare_digest(header_tok, expected)
    ):
        raise HTTPException(status_code=403, detail="invalid cron secret")
