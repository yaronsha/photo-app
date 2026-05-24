import { Container, getContainer } from "@cloudflare/containers";

export class ApiContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "5m";        // scale-to-zero idle tail — keep short (cost lever)
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only run_worker_first paths reach here; forward them to the container.
    // Single shared instance (family scale) — one name.
    return getContainer(env.API_CONTAINER, "api").fetch(request);
  },
};
