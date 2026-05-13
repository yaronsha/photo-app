# Auth: Supabase Auth (Magic Link) + JWT Middleware

Phase 3. Lock down API + frontend to family allowlist.

## Model

- Supabase Auth issues JWTs after magic-link confirmation
- Frontend stores session via `@supabase/supabase-js`
- API endpoints (JSON) auth via `Authorization: Bearer <jwt>` header
- **Image endpoints (`<img>` tags)** use one of two paths — pick one:
  - **(default, recommended)** signed-URL redirect: `GET /photo/{id}` issues 302 to short-TTL presigned R2 URL. `<img src="/photo/{id}">` follows redirect transparently. No cookie needed. Auth check at redirect-issue time.
  - **(fallback for proxy mode)** cookie auth: `POST /auth/exchange` sets httpOnly cookie carrying JWT; `<img>` includes cookie automatically. Use when bytes must proxy through Vercel (e.g. R2 keys must stay hidden, paranoid mode).
- FastAPI middleware verifies signature (via `SUPABASE_JWT_SECRET`) + checks `email` claim against `ALLOWED_EMAILS` env list
- Cron endpoints exempt from JWT auth, gated by shared secret instead

## Supabase setup

1. Dashboard → Authentication → Providers → enable Email (magic link only, disable signup if desired)
2. Authentication → URL Configuration → site URL = production Vercel URL; add `http://localhost:5173` to redirect allowlist for dev
3. Settings → API → copy:
   - `Project URL` → `SUPABASE_URL`
   - `anon public key` → `SUPABASE_ANON_KEY` (frontend)
   - `JWT secret` (Settings → API → JWT Settings) → `SUPABASE_JWT_SECRET` (backend)
4. Env: `ALLOWED_EMAILS=mom@x.com,dad@x.com,...` (comma-separated)

Disable signup means: emails not in Supabase Auth user list → no magic link sent. But also allowlist server-side because Supabase project may have other users.

## Backend

### Dep

```toml
"pyjwt[crypto]>=2.9",
```

Skip `supabase-py` SDK — overkill for verify-only.

### Middleware

```python
# app/api/auth.py
import os, jwt
from fastapi import Depends, HTTPException, Request

JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]
ALLOWED = set(e.strip().lower() for e in os.environ["ALLOWED_EMAILS"].split(","))

def _decode(token: str) -> dict:
    # PyJWT verifies exp by default. Do NOT cache — cache + expiry = stale-token validity bug.
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience="authenticated")

def require_auth(request: Request) -> dict:
    # accept Authorization header OR sb_jwt cookie (for <img> tags via cookie exchange — see below)
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get("sb_jwt")
    if not token:
        raise HTTPException(401, "missing bearer token")
    try:
        claims = _decode(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {e}")
    email = (claims.get("email") or "").lower()
    if email not in ALLOWED:
        raise HTTPException(403, "email not allowed")
    return claims
```

JWT verify is ~ms — no caching needed. Caching introduces revoked-token-stays-valid bug for process lifetime.

### Wire into endpoints

`app/api/main.py`:

```python
from app.api.auth import require_auth

@app.get("/search")
def search(..., user=Depends(require_auth)): ...

@app.get("/photo/{photo_id}")
def get_photo(..., user=Depends(require_auth)): ...

@app.get("/thumb/{photo_id}")
def get_thumb(..., user=Depends(require_auth)): ...

@app.get("/people")
def people(..., user=Depends(require_auth)): ...
```

### Cron endpoints

`/api/index-batch` uses different gate. Vercel Cron sends `Authorization: Bearer <CRON_SECRET>` automatically when `CRON_SECRET` env var is set (Vercel convention since 2024). Also accept explicit `X-Cron-Secret` header for manual triggers / GitHub Actions / curl.

```python
def require_cron(request: Request):
    expected = os.environ["CRON_SECRET"]
    bearer = request.headers.get("Authorization", "")
    bearer_tok = bearer[7:] if bearer.startswith("Bearer ") else None
    header_tok = request.headers.get("X-Cron-Secret")
    if bearer_tok != expected and header_tok != expected:
        raise HTTPException(403)

@app.post("/api/index-batch")
def index_batch(step: str, limit: int = 50, _=Depends(require_cron)): ...
```

Do **not** rely on `User-Agent: vercel-cron/1.0` or `X-Vercel-Cron` — those can be spoofed by anyone hitting the public URL.

## Frontend

### Dep

```json
"@supabase/supabase-js": "^2.45"
```

### Client

```ts
// app/web/src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js'
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)
```

Env vars (Vite requires `VITE_` prefix): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

### Login page

```tsx
// app/web/src/features/auth/LoginPage.tsx
export function LoginPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    })
    if (!error) setSent(true)
  }
  if (sent) return <p>Check your email.</p>
  return (
    <form onSubmit={submit}>
      <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
      <button type="submit">Send magic link</button>
    </form>
  )
}
```

### Auth guard + token injection

```tsx
// app/web/src/lib/session.ts
import { useEffect, useState } from 'react'
import { supabase } from './supabase'

export function useSession() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setLoading(false) })
    const { data: sub } = supabase.auth.onAuthStateChange((_, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])
  return { session, loading }
}
```

Top-level routing (`app/web/src/main.tsx` or `App.tsx`):

```tsx
function App() {
  const { session, loading } = useSession()
  if (loading) return <Spinner/>
  if (!session) return <LoginPage/>
  return <Routes>...</Routes>
}
```

API client adds bearer:

```ts
// app/web/src/api/client.ts
import { supabase } from '../lib/supabase'

export async function apiFetch(url: string, init: RequestInit = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(init.headers)
  if (session) headers.set('Authorization', `Bearer ${session.access_token}`)
  return fetch(url, { ...init, headers })
}
```

Replace all raw `fetch` in `app/web/src/api/` with `apiFetch`.

Photo + thumb `<img>` tags = problem (can't set Authorization header).

**Default = signed-URL redirect (no cookie).** `GET /photo/{id}` and `/thumb/{id}` require JWT auth, then return `302 Location: <presigned R2 URL>`. `<img src="/photo/{id}">` follows redirect to R2 directly. R2 keys still hidden behind app endpoint. Browser handles redirect transparently. Function thread doesn't hold open while bytes transfer — Vercel concurrency safer. No cookie state. R2 zero-egress wins kept.

```python
@app.get("/photo/{photo_id}")
def get_photo(photo_id: str, session=Depends(get_session), user=Depends(require_auth)):
    key = _resolve_photo_key(photo_id, session)
    url = storage.presign_get(key, expires=3600)  # adds method to Storage interface
    return RedirectResponse(url, status_code=302)
```

Add to `Storage` interface ([storage.md](storage.md)): `presign_get(key, expires) -> str`. LocalStorage returns a local URL (dev only, FastAPI mounts `data/` as static); R2Storage calls `client.generate_presigned_url`.

**Fallback = cookie path** (use when redirects unsuitable, e.g. CSP forbids cross-origin img, or audit demands per-byte auth):

```python
@app.post("/auth/exchange")
def exchange(request: Request, response: Response):
    token = request.headers.get("Authorization", "")[7:]
    _decode(token)  # validate
    response.set_cookie("sb_jwt", token, httponly=True, secure=True, samesite="lax", max_age=3600)
    return {"ok": True}
```

Frontend calls `/auth/exchange` after login. `require_auth` already reads `Authorization` header OR `sb_jwt` cookie (see middleware above). `<img>` proxies via FastAPI streaming R2 bytes.

## Verification

```bash
# 1. Unauthenticated rejected
curl -i http://localhost:8000/search
# expect 401

# 2. Bad token rejected
curl -i -H "Authorization: Bearer junk" http://localhost:8000/search
# expect 401

# 3. Non-allowlisted email rejected
# manually craft JWT with non-allowed email
# expect 403

# 4. Valid magic-link flow
# - load frontend, enter allowlisted email
# - click magic link in email
# - redirected back, session set
# - /search returns results
# - <img> loads photo

# 5. Cron header
curl -X POST -H "X-Cron-Secret: $CRON_SECRET" \
  "http://localhost:8000/api/index-batch?step=caption&limit=2"
# expect 200
curl -X POST "http://localhost:8000/api/index-batch?step=caption"
# expect 403
```

## Critical files

- `app/api/auth.py` **(new)**
- `app/api/main.py` (add `Depends(require_auth)` to all data endpoints)
- `app/web/src/lib/supabase.ts`, `session.ts` **(new)**
- `app/web/src/features/auth/LoginPage.tsx` **(new)**
- `app/web/src/api/client.ts` (add bearer injection)
- `pyproject.toml` (+`pyjwt[crypto]`)
- `app/web/package.json` (+`@supabase/supabase-js`)

## Risks

- **JWT secret in env vs JWKS:** Supabase HS256 default = shared secret. Anyone with `SUPABASE_JWT_SECRET` can mint tokens. Treat as production secret. Rotate via Supabase dashboard if leaked.
- **Cookie + CORS:** if frontend on different domain than API, need `SameSite=None; Secure` + `Access-Control-Allow-Credentials`. On Vercel same origin = fine.
- **Magic link emails to spam:** configure custom SMTP in Supabase, or accept Supabase default (rate-limited).
- **Allowlist drift:** `ALLOWED_EMAILS` env list = manual. Add a person = redeploy. Future: move to Postgres table.
