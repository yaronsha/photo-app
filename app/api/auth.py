"""JWT verification + email allowlist for Supabase-issued tokens.

Auth is **opt-in**: if `SUPABASE_JWT_SECRET` is unset, `require_auth` is a
no-op. This preserves the "run locally with env vars only" rollback path
(see docs/migration/README.md "Critical invariant").

When `SUPABASE_JWT_SECRET` is set:
  - bearer in `Authorization` header OR `sb_jwt` cookie is decoded (HS256)
  - `email` claim must be in `ALLOWED_EMAILS` (comma-separated env list)

Cron endpoints use `require_cron` instead — shared bearer in
`Authorization` header or `X-Cron-Secret`, compared to `CRON_SECRET`.
"""
from __future__ import annotations

import hmac
import os

import jwt
from fastapi import HTTPException, Request


def _auth_enabled() -> bool:
    return bool(os.environ.get("SUPABASE_JWT_SECRET"))


def _allowed_emails() -> set[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("sb_jwt")


def require_auth(request: Request) -> dict:
    """FastAPI dependency. Returns decoded claims (or `{}` if auth disabled)."""
    if not _auth_enabled():
        return {}

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    secret = os.environ["SUPABASE_JWT_SECRET"]
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
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
