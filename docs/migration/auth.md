# Auth: Supabase Auth (Google OAuth) + JWT Middleware

Phase 3. Lock down API + frontend to family allowlist via Google sign-in.

**Status:** ✅ shipped. Implementation in `app/api/auth.py`, `app/web/src/lib/{supabase,session}.ts`, `app/web/src/features/auth/LoginPage.tsx`.

## Model

- Supabase Auth issues JWTs after Google OAuth completes
- Frontend stores session via `@supabase/supabase-js` (Google provider, no magic links)
- API endpoints (JSON) auth via `Authorization: Bearer <jwt>` header
- **Image endpoints (`/photo/{id}`, `/thumb/{id}`)** use **signed-URL redirect**: handler verifies JWT, then returns 302 to a short-TTL presigned R2 URL. `<img src="/photo/{id}">` follows the redirect transparently — no cookie needed, R2 keys stay hidden, function thread isn't tied up streaming bytes.
- A `POST /auth/exchange` endpoint exists as a fallback for cookie-based `<img>` auth (`require_auth` already accepts an `sb_jwt` cookie) but is not used by the default flow.
- FastAPI middleware verifies signature (`SUPABASE_JWT_SECRET`, HS256) + checks `email` claim against `ALLOWED_EMAILS`
- Cron endpoints exempt from JWT auth; gated by shared `CRON_SECRET`

## Opt-in by env var (rollback invariant)

Auth is **off by default**. If `SUPABASE_JWT_SECRET` is unset, `require_auth` is a no-op and every endpoint is open — preserving the local-dev rollback path documented in [README.md](README.md). Setting `SUPABASE_JWT_SECRET` flips enforcement on. Same applies to `CRON_SECRET` for `require_cron`.

This means: existing local CLI + uvicorn workflow continues to work with zero config changes. Vercel deploy sets the env vars → enforcement on.

## Supabase setup

1. Dashboard → Authentication → Providers → enable **Google**, paste Google OAuth client id/secret from Google Cloud Console (Authorized redirect URI: `https://<ref>.supabase.co/auth/v1/callback`)
2. Authentication → URL Configuration → site URL = production Vercel URL; add `http://localhost:5173` to redirect allowlist for dev
3. Settings → API → copy:
   - `Project URL` → `SUPABASE_URL` (backend) / `VITE_SUPABASE_URL` (frontend)
   - `anon public key` → `VITE_SUPABASE_ANON_KEY` (frontend)
   - `JWT secret` (Settings → API → JWT Settings) → `SUPABASE_JWT_SECRET` (backend)
4. Env: `ALLOWED_EMAILS=mom@x.com,dad@x.com,...` (comma-separated, server-side allowlist)

Server-side allowlist matters even if you restrict Google sign-in by Workspace domain — Supabase issues tokens for any Google user that signs in successfully, so the email-claim check is the actual gate.

## Backend

### Dep

```toml
"pyjwt[crypto]>=2.9",
```

(Already in `pyproject.toml`.) No `supabase-py` SDK needed — we only verify, not call the API.

### Middleware — `app/api/auth.py`

Two FastAPI dependencies:

- `require_auth(request) -> dict` — verifies the JWT and returns claims, raising 401/403 on rejection. Bearer can come from the `Authorization` header OR the `sb_jwt` cookie. Bypassed when `SUPABASE_JWT_SECRET` is unset.
- `require_cron(request) -> None` — verifies `Authorization: Bearer <CRON_SECRET>` or `X-Cron-Secret`. Bypassed when `CRON_SECRET` unset. Uses `hmac.compare_digest` for constant-time comparison.

JWT verify is ~ms — no caching. Caching introduces a revoked-token-stays-valid window.

### Wiring

In `app/api/main.py` every data endpoint takes `_user=Depends(require_auth)`:

```python
@app.get("/people")
def people_endpoint(_user=Depends(require_auth)): ...

@app.get("/search")
def search_endpoint(..., _user=Depends(require_auth)): ...

@app.get("/photo/{photo_id}")
def photo(photo_id: str, _user=Depends(require_auth)): ...
```

Image endpoints (`/photo/{id}`, `/thumb/{id}`) return 302:

```python
@app.get("/photo/{photo_id}")
def photo(photo_id: str, _user=Depends(require_auth)):
    ...
    url = storage.presign_get(key, expires=3600)
    return RedirectResponse(url, status_code=302)
```

`Storage.presign_get(key, expires)` is implemented for both `LocalStorage` (returns `/local/{key}`) and `R2Storage` (calls `client.generate_presigned_url`).

For local dev with `STORAGE_BACKEND=local` we mount `/local/` as `StaticFiles(directory=data_dir)`. **Skipped when `SUPABASE_JWT_SECRET` is set** — `/local/` is unauthenticated by design, so we refuse to expose it alongside JWT-gated endpoints (use R2 in prod).

### Cron endpoints

`require_cron` is exported from `app/api/main` for phase 4 (compute refactor) to attach to `/api/index-batch`. Vercel Cron sends `Authorization: Bearer <CRON_SECRET>` automatically. Manual / GitHub Actions triggers can use `X-Cron-Secret`.

Do **not** rely on `User-Agent: vercel-cron/1.0` or `X-Vercel-Cron` — both can be spoofed by anyone hitting the public URL.

## Frontend

### Dep

```json
"@supabase/supabase-js": "^2.45"
```

### Files

- `app/web/src/lib/supabase.ts` — creates the client iff `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` are set. Exports `supabase` (or `null`) and `isAuthEnabled`. Mirrors the backend's opt-in model.
- `app/web/src/lib/session.ts` — `useSession()` hook returns `{ session, loading }`. Subscribes to `onAuthStateChange`.
- `app/web/src/features/auth/LoginPage.tsx` — single "Sign in with Google" button calling `supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin } })`.
- `app/web/src/App.tsx` — gates routes: if `isAuthEnabled && !session` → `<LoginPage/>`, else app.
- `app/web/src/api/client.ts` — `apiFetch` reads the active session and injects `Authorization: Bearer <access_token>` on every JSON request.

Env vars (Vite requires `VITE_` prefix): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

`<img>` tags use `/photo/{id}` and `/thumb/{id}` — those issue a 302 redirect to a presigned URL, so no Authorization header is needed on the browser's redirect-following request.

## Verification

```bash
# 1. Unauthenticated rejected (with SUPABASE_JWT_SECRET set)
curl -i http://localhost:8000/search
# expect 401

# 2. Bad token rejected
curl -i -H "Authorization: Bearer junk" http://localhost:8000/search
# expect 401

# 3. Non-allowlisted email rejected
# manually craft JWT with non-allowed email
# expect 403

# 4. Valid Google OAuth flow
# - load frontend, click "Sign in with Google"
# - Google consent → redirect back, session set
# - /search returns results
# - <img> loads via /photo/{id} → 302 → R2

# 5. Cron header
curl -X POST -H "X-Cron-Secret: $CRON_SECRET" \
  "http://localhost:8000/api/index-batch?step=caption&limit=2"
# expect 200 (once phase 4 ships /api/index-batch)
curl -X POST "http://localhost:8000/api/index-batch"
# expect 403
```

Automated coverage: `tests/test_auth.py` (token rejection paths, allowlist, cookie auth, 302 redirect on photo/thumb, cron secret accept/reject).

## Critical files

- `app/api/auth.py` (new)
- `app/api/main.py` (added `Depends(require_auth)`; switched `/photo` + `/thumb` to 302 presign redirect; mounted `/local/` in dev)
- `app/web/src/lib/supabase.ts`, `app/web/src/lib/session.ts` (new)
- `app/web/src/features/auth/LoginPage.tsx` (new)
- `app/web/src/api/client.ts` (bearer injection)
- `pyproject.toml` (+`pyjwt[crypto]`)
- `app/web/package.json` (+`@supabase/supabase-js`)
- `tests/test_auth.py` (new)

## Risks

- **JWT secret in env vs JWKS:** Supabase HS256 default = shared secret. Anyone with `SUPABASE_JWT_SECRET` can mint tokens. Treat as production secret; rotate via Supabase dashboard if leaked.
- **Cookie + CORS:** Vercel same-origin = fine. If the frontend ever moves to a separate domain, set `SameSite=None; Secure` + `Access-Control-Allow-Credentials`.
- **Allowlist drift:** `ALLOWED_EMAILS` env list = manual. Adding a person = redeploy. Future: move to Postgres table.
- **Local `/local/` mount:** unauthenticated by design (dev only). The conditional skip when `SUPABASE_JWT_SECRET` is set prevents accidentally exposing it next to JWT-gated routes.
