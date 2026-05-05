import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Use node environment: native fetch + AbortSignal work correctly with msw/node.
    // mock-socket's Server can replace globalThis.WebSocket freely in node.
    environment: "node",
    globals: false,
    include: ["__tests__/**/*.test.ts"],
    testTimeout: 10_000,
  },
});
