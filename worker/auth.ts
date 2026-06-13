// JWT verification + email allowlist for Supabase-issued tokens — a faithful
// TS port of app/api/auth.py, run in the Worker isolate so /thumb/* can be
// served (and gated) at the edge without touching the container.
//
// Supabase signs access tokens with asymmetric keys (ES256/RS256) on current
// projects, fetched from the project's JWKS endpoint. We verify strictly
// against the *configured* SUPABASE_URL — never the token's own `iss` claim —
// so an attacker can't point verification at a JWKS they control.
//
// The HS256 shared-secret path from auth.py is intentionally dropped: this
// project uses asymmetric keys, and omitting it keeps the surface small.
//
// Auth is opt-in: if SUPABASE_URL (and SUPABASE_JWKS_URL) is unset, auth is
// disabled and every request is allowed. This preserves the "run locally with
// env vars only" rollback invariant (see docs/migration/README.md).
import { createRemoteJWKSet, jwtVerify, errors } from "jose";

export interface AuthEnv {
  SUPABASE_URL?: string;
  SUPABASE_JWKS_URL?: string;
  ALLOWED_EMAILS?: string;
}

export type AuthResult =
  | { ok: true; claims: Record<string, unknown> }
  | { ok: false; status: number; detail: string };

// createRemoteJWKSet caches keys internally; reuse one per JWKS URL so we don't
// re-fetch the key set on every request (mirrors auth.py's _jwks_clients).
const _jwksCache = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

/**
 * JWKS endpoint, from explicit override or derived from SUPABASE_URL.
 * Derived only from configured trust material — never the token's `iss`.
 */
function jwksUrl(env: AuthEnv): string | null {
  if (env.SUPABASE_JWKS_URL) return env.SUPABASE_JWKS_URL;
  if (env.SUPABASE_URL) {
    return env.SUPABASE_URL.replace(/\/+$/, "") + "/auth/v1/.well-known/jwks.json";
  }
  return null;
}

function getJwks(url: string): ReturnType<typeof createRemoteJWKSet> {
  let jwks = _jwksCache.get(url);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(url));
    _jwksCache.set(url, jwks);
  }
  return jwks;
}

function allowedEmails(env: AuthEnv): Set<string> {
  const raw = env.ALLOWED_EMAILS ?? "";
  return new Set(
    raw
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter((e) => e.length > 0),
  );
}

function getCookie(request: Request, name: string): string | null {
  const header = request.headers.get("Cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    if (part.slice(0, idx).trim() === name) return part.slice(idx + 1).trim();
  }
  return null;
}

function extractToken(request: Request): string | null {
  const auth = request.headers.get("Authorization") ?? "";
  if (auth.startsWith("Bearer ")) return auth.slice(7);
  return getCookie(request, "sb_jwt");
}

/**
 * Verify the request's JWT + email allowlist.
 *
 * Returns `{ ok: true, claims }` (claims is `{}` when auth is disabled) or
 * `{ ok: false, status, detail }` with 401 for missing/invalid/expired tokens
 * and 403 for a validly-signed token whose email is not allowlisted — matching
 * the status codes raised by app/api/auth.py.
 */
export async function verifyAuth(request: Request, env: AuthEnv): Promise<AuthResult> {
  const url = jwksUrl(env);
  if (!url) {
    // Auth disabled (no configured trust material) — local-dev passthrough.
    return { ok: true, claims: {} };
  }

  const token = extractToken(request);
  if (!token) {
    return { ok: false, status: 401, detail: "missing bearer token" };
  }

  let claims: Record<string, unknown>;
  try {
    const { payload } = await jwtVerify(token, getJwks(url), {
      audience: "authenticated",
      algorithms: ["ES256", "RS256"],
    });
    claims = payload as Record<string, unknown>;
  } catch (err) {
    if (err instanceof errors.JWTExpired) {
      return { ok: false, status: 401, detail: "token expired" };
    }
    // A JWKS fetch failure is an infra outage rather than a bad token, but both
    // surface as 401 (matching auth.py). Distinguish only in the detail string.
    if (err instanceof errors.JOSEError) {
      return { ok: false, status: 401, detail: `invalid token: ${err.message}` };
    }
    return { ok: false, status: 401, detail: "could not fetch signing key" };
  }

  // Fail closed: with auth enabled, an empty allowlist denies everyone rather
  // than admitting any validly-signed token (a forgotten ALLOWED_EMAILS must
  // not silently expose the library).
  const allowed = allowedEmails(env);
  const email = String(claims.email ?? "").toLowerCase();
  if (allowed.size === 0 || !allowed.has(email)) {
    return { ok: false, status: 403, detail: "email not allowed" };
  }

  return { ok: true, claims };
}
