// JWT verification + email allowlist for Supabase-issued tokens.
// Verifies strictly against the *configured* SUPABASE_URL — never the token's
// own `iss` claim — so an attacker can't redirect verification to a JWKS they
// control. Auth is disabled when SUPABASE_URL is unset (local-dev passthrough).
import { createRemoteJWKSet, jwtVerify, errors } from "jose";

export interface AuthEnv {
  SUPABASE_URL?: string;
  SUPABASE_JWKS_URL?: string;
  ALLOWED_EMAILS?: string;
}

export type AuthResult =
  | { ok: true; claims: Record<string, unknown> }
  | { ok: false; status: number; detail: string };

// createRemoteJWKSet caches keys internally; reuse one per JWKS URL.
const _jwksCache = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

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

// Returns { ok: true, claims } or { ok: false, status, detail }.
// 401 = missing/invalid/expired token. 403 = valid token, email not allowlisted.
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
    if (err instanceof errors.JOSEError) {
      return { ok: false, status: 401, detail: `invalid token: ${err.message}` };
    }
    return { ok: false, status: 401, detail: "could not fetch signing key" };
  }

  // Fail closed: empty allowlist denies everyone rather than admitting all valid tokens.
  const allowed = allowedEmails(env);
  const email = String(claims.email ?? "").toLowerCase();
  if (allowed.size === 0 || !allowed.has(email)) {
    return { ok: false, status: 403, detail: "email not allowed" };
  }

  return { ok: true, claims };
}
