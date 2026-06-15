import { defineConfig } from "vitest/config";

// Worker unit tests only. app/web owns its own (Playwright) tests, so scope
// the include here to keep the two runners from colliding.
export default defineConfig({
  test: {
    environment: "node",
    include: ["worker/**/*.test.ts"],
  },
});
