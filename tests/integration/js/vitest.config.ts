import { defineConfig } from "vitest/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Resolve to the pnpm workspace root so all packages share one React instance.
const JS_ROOT = fileURLToPath(new URL("..", import.meta.url));
const PNPM_STORE = path.join(JS_ROOT, "node_modules", ".pnpm");

// react@18 is the only version in this workspace.
const REACT_18 = path.join(
	PNPM_STORE,
	"react@18.3.1",
	"node_modules",
	"react",
);
const REACT_DOM_18 = path.join(
	PNPM_STORE,
	"react-dom@18.3.1_react@18.3.1",
	"node_modules",
	"react-dom",
);

export default defineConfig({
	test: {
		globals: true,
		// Default env for React component tests.
		environment: "jsdom",
		setupFiles: ["./vitest.setup.ts"],
		include: ["**/*.spec.{ts,tsx}", "**/*.test.{ts,tsx}"],
		testTimeout: 10_000,
		// Treat the runtime-client spec in node environment (AbortSignal compat).
		environmentMatchGlobs: [
			["**/designer-runtime-integration.spec.ts", "node"],
		],
	},
	resolve: {
		alias: {
			// Force all workspace packages to share one react + react-dom instance.
			react: REACT_18,
			"react-dom": REACT_DOM_18,
			"react/jsx-runtime": path.join(REACT_18, "jsx-runtime.js"),
			"react/jsx-dev-runtime": path.join(REACT_18, "jsx-dev-runtime.js"),
		},
	},
});
