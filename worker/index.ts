import { Container, getContainer } from "@cloudflare/containers";

// Secrets/vars to forward from the Worker isolate into the container process.
// Cloudflare does NOT auto-forward these: `wrangler secret put` binds a value
// to the Worker's `env`, but the container is a separate sandbox whose env is
// only `Dockerfile ENV + this.envVars`. Without this bridge the API sees no
// DATABASE_URL and (used to) silently fall back to an empty sqlite db.
const CONTAINER_ENV_KEYS = [
  "DATABASE_URL",
  "VECTOR_BACKEND",
  "STORAGE_BACKEND",
  "R2_ACCOUNT_ID",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
  "R2_BUCKET",
  "SUPABASE_URL",
  "ALLOWED_EMAILS",
  "OPENAI_API_KEY",
] as const;

function pickEnv(env: Env): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of CONTAINER_ENV_KEYS) {
    const value = (env as Record<string, unknown>)[key];
    // Skip undefined/empty so unset keys fall through to the Dockerfile ENV
    // defaults (e.g. VECTOR_BACKEND, STORAGE_BACKEND) instead of being clobbered.
    if (typeof value === "string" && value.length > 0) out[key] = value;
  }
  return out;
}

export class ApiContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "5m";        // scale-to-zero idle tail — keep short (cost lever)

  // `this.env` is populated by the Durable Object base ctor (super) before
  // subclass field initializers run, so reading secrets here is safe.
  envVars = pickEnv(this.env);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only run_worker_first paths reach here; forward them to the container.
    // Single shared instance (family scale) — one name.
    return getContainer(env.API_CONTAINER, "api").fetch(request);
  },
};
