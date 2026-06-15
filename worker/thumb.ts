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

  const id = new URL(request.url).pathname.slice("/thumb/".length);
  if (!ID_RE.test(id)) {
    return new Response("bad thumbnail id", { status: 400 });
  }

  const cache = caches.default;
  const cached = await cache.match(request);
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
  ctx.waitUntil(cache.put(request, response.clone()));
  return response;
}
