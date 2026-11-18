// Serve /thumb/{id} from R2 + edge cache in the Worker isolate.
//
// Flow: auth → caches.default.match → R2_THUMBS.get → container fallthrough
// Auth runs before any cache read so cached bytes can't leak unauthenticated.
import { verifyAuth, type AuthEnv } from "./auth";

export interface ThumbEnv extends AuthEnv {
  R2_THUMBS: R2Bucket;
}

// Photo ids are 16 lowercase hex chars (sha256 prefix). Validate before keying R2.
const ID_RE = /^[0-9a-f]{16}$/;

// Strip query string from cache key: /thumb/{id}?anything would otherwise
// cache as a separate 1-year-immutable entry for identical R2 bytes.
function thumbCacheKey(origin: string, id: string): Request {
  return new Request(`${origin}/thumb/${id}`);
}

const HIDE_RE = /^\/photo\/([0-9a-f]{16})\/hide$/;

/** Proxy POST /photo/{id}/hide to the container (which checks admin, sets the
 *  flag and deletes thumbs/{id}.jpg from R2). On success, also drop this
 *  colo's edge-cache copy of the thumb so the fast path stops serving it.
 *  Returns null for any other request. Other colos and browsers that already
 *  cached the thumb keep it until their cache expires. */
export async function handleHide(
  request: Request,
  ctx: ExecutionContext,
  forwardToContainer: (request: Request) => Response | Promise<Response>,
): Promise<Response | null> {
  const url = new URL(request.url);
  const m = request.method === "POST" ? HIDE_RE.exec(url.pathname) : null;
  if (!m) return null;
  const response = await forwardToContainer(request);
  if (response.ok) {
    ctx.waitUntil(caches.default.delete(thumbCacheKey(url.origin, m[1])));
  }
  return response;
}

// `forwardToContainer` is injected so this handler is unit-testable without
// the @cloudflare/containers runtime import.
export async function handleThumb(
  request: Request,
  env: ThumbEnv,
  ctx: ExecutionContext,
  forwardToContainer: (request: Request) => Response | Promise<Response>,
): Promise<Response> {
  const auth = await verifyAuth(request, env);
  if (!auth.ok) {
    return new Response(auth.detail, { status: auth.status });
  }

  const parsed = new URL(request.url);
  const id = parsed.pathname.slice("/thumb/".length);
  if (!ID_RE.test(id)) {
    return new Response("bad thumbnail id", { status: 400 });
  }

  const cacheKey = thumbCacheKey(parsed.origin, id);
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const obj = await env.R2_THUMBS.get(`thumbs/${id}.jpg`);
  if (obj === null) {
    // Not in R2 yet — fall through to container for on-demand generation. Don't cache the 302.
    return forwardToContainer(request);
  }

  const response = new Response(obj.body, {
    headers: {
      "Content-Type": "image/jpeg",
      // id is a content hash → same id always maps to same bytes → immutable is safe.
      "Cache-Control": "public, max-age=31536000, immutable",
      ETag: obj.httpEtag,
    },
  });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}
