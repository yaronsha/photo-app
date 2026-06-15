import { Container, getContainer } from "@cloudflare/containers";
import { handleThumb } from "./thumb";

// Secrets to bridge from Worker env into the container sandbox.
// The container only sees Dockerfile ENV + this.envVars — Worker secrets are not
// auto-forwarded. VECTOR_BACKEND/STORAGE_BACKEND are baked into the image.
const CONTAINER_ENV_KEYS = [
  "DATABASE_URL",
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
      // Skip unset/empty so Dockerfile ENV defaults aren't clobbered.
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
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/thumb/")) {
      return handleThumb(request, env, ctx, (req) =>
        getContainer(env.API_CONTAINER, "api").fetch(req),
      );
    }

    return getContainer(env.API_CONTAINER, "api").fetch(request);
  },
};
