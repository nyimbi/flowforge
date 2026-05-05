import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
  resolve: {
    alias: {
      "@flowforge/types": new URL(
        "../flowforge-types/src/index.ts",
        import.meta.url,
      ).pathname,
    },
  },
});
