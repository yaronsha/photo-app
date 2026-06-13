// Serve /thumb/{id} straight from the R2 binding in the Worker isolate, with
// edge caching, bypassing the API container entirely (see issue #51).
//
// Flow:
//   verify auth (every request — private family photos)
//   → caches.default.match  → HIT: return (edge, ~0ms)
//   → MISS: R2_THUMBS.get("thumbs/{id}.jpg")
//       found: return bytes, Cache-Control immutable, ctx.waitUntil(cache.put)
//       null:  forward to the container's on-demand generation path; don't cache
//
// Auth runs BEFORE any cache read, so a cached entry can never leak to an
// unauthenticated caller even though the cache key is the URL alone.
import { verifyAuth, type AuthEnv } from "./auth";

export interface ThumbEnv extends AuthEnv {
  R2_THUMBS: R2Bucket;
}

// Photo ids are sha256(file_bytes)[:16] — 16 lowercase hex chars
// (see app/indexer/CLAUDE.md). Validate before building the R2 key.
const ID_RE = /^[0-9a-f]{16}$/;

/**
 * Handle GET /thumb/{id}. `forwardToContainer` is the fall-through used when
 * the thumb hasn't been pre-generated yet; it's injected so the handler stays
 * free of the @cloudflare/containers runtime import and is unit-testable.
 */
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

  const id = new URL(request.url).pathname.slice("/thumb/".length);
  if (!ID_RE.test(id)) {
    return new Response("bad thumbnail id", { status: 400 });
  }

  const cache = caches.default;
  const cached = await cache.match(request);
  if (cached) return cached;

  const obj = await env.R2_THUMBS.get(`thumbs/${id}.jpg`);
  if (obj === null) {
    // Not pre-generated yet — fall through to the container's on-demand
    // generation path. Rare once `--step thumb` has run over the corpus.
    // Do NOT cache the resulting 302.
    return forwardToContainer(request);
  }

  const response = new Response(obj.body, {
    headers: {
      "Content-Type": "image/jpeg",
      // Thumb keys are content-addressed (id = sha256 of the source bytes), so
      // the same id always maps to the same image — safe to mark immutable.
      "Cache-Control": "public, max-age=31536000, immutable",
      ETag: obj.httpEtag,
    },
  });
  ctx.waitUntil(cache.put(request, response.clone()));
  return response;
}
