import { describe, it, expect, beforeAll, vi } from "vitest";
import { SignJWT, exportJWK, generateKeyPair } from "jose";
import { verifyAuth } from "./auth";

const SUPABASE_URL = "https://test.supabase.co";
const JWKS_URL = SUPABASE_URL + "/auth/v1/.well-known/jwks.json";
const ALLOWED = "alice@example.com, Bob@Example.com";

let privateKey: CryptoKey;

beforeAll(async () => {
  const { privateKey: priv, publicKey } = await generateKeyPair("ES256", {
    extractable: true,
  });
  privateKey = priv;
  const jwk = await exportJWK(publicKey);
  jwk.alg = "ES256";
  jwk.use = "sig";
  const jwks = { keys: [jwk] };

  // createRemoteJWKSet fetches the JWKS over the global fetch — serve our
  // generated public key and reject anything else (proves the verifier only
  // ever talks to the configured JWKS URL).
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const u = typeof input === "string" ? input : input.toString();
      if (u === JWKS_URL) {
        return new Response(JSON.stringify(jwks), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      throw new Error("unexpected fetch: " + u);
    }),
  );
});

async function makeToken({
  email = "alice@example.com",
  audience = "authenticated",
  expSeconds,
}: { email?: string; audience?: string; expSeconds?: number } = {}): Promise<string> {
  const jwt = new SignJWT({ email })
    .setProtectedHeader({ alg: "ES256" })
    .setIssuedAt()
    .setAudience(audience);
  jwt.setExpirationTime(expSeconds ?? "2h");
  return jwt.sign(privateKey);
}

function bearerRequest(token?: string): Request {
  return new Request("https://app.example/thumb/00112233aabbccdd", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

const env = { SUPABASE_URL, ALLOWED_EMAILS: ALLOWED };

describe("verifyAuth", () => {
  it("accepts a valid token for an allowlisted email", async () => {
    const res = await verifyAuth(bearerRequest(await makeToken()), env);
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.claims.email).toBe("alice@example.com");
  });

  it("accepts the sb_jwt cookie when no Authorization header is present", async () => {
    const token = await makeToken();
    const req = new Request("https://app.example/thumb/00112233aabbccdd", {
      headers: { Cookie: `other=1; sb_jwt=${token}` },
    });
    const res = await verifyAuth(req, env);
    expect(res.ok).toBe(true);
  });

  it("is case-insensitive on the email allowlist", async () => {
    // Token email "BOB@example.com" vs allowlist entry "Bob@Example.com".
    const res = await verifyAuth(bearerRequest(await makeToken({ email: "BOB@example.com" })), env);
    expect(res.ok).toBe(true);
  });

  it("returns 401 when no token is supplied", async () => {
    const res = await verifyAuth(bearerRequest(), env);
    expect(res).toEqual({ ok: false, status: 401, detail: "missing bearer token" });
  });

  it("returns 401 for an expired token", async () => {
    const token = await makeToken({ expSeconds: Math.floor(Date.now() / 1000) - 60 });
    const res = await verifyAuth(bearerRequest(token), env);
    expect(res).toEqual({ ok: false, status: 401, detail: "token expired" });
  });

  it("returns 401 for a tampered signature", async () => {
    const token = await makeToken();
    const tampered = token.slice(0, -3) + (token.endsWith("A") ? "BBB" : "AAA");
    const res = await verifyAuth(bearerRequest(tampered), env);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.status).toBe(401);
  });

  it("returns 401 for the wrong audience", async () => {
    const token = await makeToken({ audience: "not-authenticated" });
    const res = await verifyAuth(bearerRequest(token), env);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.status).toBe(401);
  });

  it("returns 403 for a valid token whose email is not allowlisted", async () => {
    const token = await makeToken({ email: "mallory@evil.com" });
    const res = await verifyAuth(bearerRequest(token), env);
    expect(res).toEqual({ ok: false, status: 403, detail: "email not allowed" });
  });

  it("fails closed: empty allowlist denies an otherwise-valid token", async () => {
    const res = await verifyAuth(bearerRequest(await makeToken()), {
      SUPABASE_URL,
      ALLOWED_EMAILS: "",
    });
    expect(res).toEqual({ ok: false, status: 403, detail: "email not allowed" });
  });

  it("passes through (auth disabled) when SUPABASE_URL is unset", async () => {
    const res = await verifyAuth(bearerRequest(), { ALLOWED_EMAILS: ALLOWED });
    expect(res).toEqual({ ok: true, claims: {} });
  });
});
