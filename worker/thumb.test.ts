import { describe, it, expect, vi, beforeEach } from "vitest";
import { handleThumb, type ThumbEnv } from "./thumb";

const VALID_ID = "00112233aabbccdd";
const THUMB_URL = `https://app.example/thumb/${VALID_ID}`;

// Minimal in-memory stand-ins for the Cloudflare runtime objects the handler
// touches. These live only in the test (node) environment.
function makeCache() {
  const store = new Map<string, Response>();
  return {
    store,
    match: vi.fn(async (req: Request) => store.get(req.url)),
    put: vi.fn(async (req: Request, res: Response) => {
      store.set(req.url, res);
    }),
  };
}

function makeCtx() {
  const tasks: Promise<unknown>[] = [];
  return {
    tasks,
    waitUntil: vi.fn((p: Promise<unknown>) => tasks.push(p)),
  } as unknown as ExecutionContext & { tasks: Promise<unknown>[] };
}

function r2Object(body: string, etag = '"deadbeef"') {
  return { body, httpEtag: etag };
}

let cache: ReturnType<typeof makeCache>;

beforeEach(() => {
  cache = makeCache();
  vi.stubGlobal("caches", { default: cache });
});

// Auth disabled (no SUPABASE_URL) for the storage-path tests, so we exercise
// thumb logic without needing a signed JWT.
const openEnv = (get: ThumbEnv["R2_THUMBS"]["get"]): ThumbEnv => ({
  R2_THUMBS: { get } as unknown as R2Bucket,
});

describe("handleThumb", () => {
  it("serves bytes from R2 on a cache miss, with immutable caching headers", async () => {
    const get = vi.fn(async () => r2Object("JPEGBYTES"));
    const ctx = makeCtx();
    const forward = vi.fn();

    const res = await handleThumb(new Request(THUMB_URL), openEnv(get), ctx, forward);

    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("image/jpeg");
    expect(res.headers.get("Cache-Control")).toBe("public, max-age=31536000, immutable");
    expect(res.headers.get("ETag")).toBe('"deadbeef"');
    expect(await res.text()).toBe("JPEGBYTES");
    expect(get).toHaveBeenCalledWith(`thumbs/${VALID_ID}.jpg`);
    expect(forward).not.toHaveBeenCalled();

    // The response is written to the edge cache via waitUntil.
    expect(ctx.waitUntil).toHaveBeenCalledTimes(1);
    await Promise.all((ctx as unknown as { tasks: Promise<unknown>[] }).tasks);
    expect(cache.put).toHaveBeenCalledTimes(1);
  });

  it("returns the cached response on a hit without touching R2", async () => {
    cache.store.set(THUMB_URL, new Response("CACHED", { status: 200 }));
    const get = vi.fn();
    const forward = vi.fn();

    const res = await handleThumb(new Request(THUMB_URL), openEnv(get), makeCtx(), forward);

    expect(await res.text()).toBe("CACHED");
    expect(get).not.toHaveBeenCalled();
    expect(forward).not.toHaveBeenCalled();
  });

  it("falls through to the container when the thumb is not yet generated, without caching", async () => {
    const get = vi.fn(async () => null);
    const forward = vi.fn(async () => new Response("redirect", { status: 302 }));
    const ctx = makeCtx();

    const res = await handleThumb(new Request(THUMB_URL), openEnv(get), ctx, forward);

    expect(res.status).toBe(302);
    expect(forward).toHaveBeenCalledTimes(1);
    expect(ctx.waitUntil).not.toHaveBeenCalled();
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("rejects a malformed id with 400 before hitting R2", async () => {
    const get = vi.fn();
    const forward = vi.fn();

    for (const bad of ["short", "ZZZZ2233aabbccdd", "00112233aabbccdd.jpg", "../secret"]) {
      const res = await handleThumb(
        new Request(`https://app.example/thumb/${bad}`),
        openEnv(get),
        makeCtx(),
        forward,
      );
      expect(res.status).toBe(400);
    }
    expect(get).not.toHaveBeenCalled();
    expect(forward).not.toHaveBeenCalled();
  });

  it("strips query string from cache key so variant URLs share one cache entry", async () => {
    const get = vi.fn(async () => r2Object("JPEGBYTES"));
    const ctx = makeCtx();
    const forward = vi.fn();

    // First request: URL with query string — should miss cache, hit R2, write to cache.
    await handleThumb(
      new Request(`${THUMB_URL}?v=bust`),
      openEnv(get),
      ctx,
      forward,
    );
    await Promise.all((ctx as unknown as { tasks: Promise<unknown>[] }).tasks);
    expect(cache.put).toHaveBeenCalledTimes(1);

    // Second request: bare URL — should hit the cache entry written above.
    get.mockClear();
    const res = await handleThumb(new Request(THUMB_URL), openEnv(get), makeCtx(), forward);
    expect(await res.text()).toBe("JPEGBYTES");
    expect(get).not.toHaveBeenCalled();
  });

  it("enforces auth before any cache read or R2 access", async () => {
    const get = vi.fn();
    const forward = vi.fn();
    // Auth enabled but no token → 401, and crucially R2/cache are never touched.
    const env = {
      SUPABASE_URL: "https://test.supabase.co",
      ALLOWED_EMAILS: "alice@example.com",
      R2_THUMBS: { get } as unknown as R2Bucket,
    };

    const res = await handleThumb(new Request(THUMB_URL), env, makeCtx(), forward);

    expect(res.status).toBe(401);
    expect(cache.match).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
    expect(forward).not.toHaveBeenCalled();
  });
});
