import { defineConfig } from "vitest/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Resolve to the pnpm workspace root so all packages share one React instance.
const JS_ROOT = fileURLToPath(new URL("..", import.meta.url));
const PNPM_STORE = path.join(JS_ROOT, "node_modules", ".pnpm");

// react@18 is what the legacy integration specs (renderer-form-flow,
// step-adapter-runtime, designer-runtime-integration) target via
// @testing-library/react@16. The audit-2026 E-43 / JS-03 contract test
// imports React 19 via the `react19` / `react19-dom/client` aliases below
// so the hook is exercised under R19's actual hook implementations without
// disturbing the other specs.
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
const REACT_19 = path.join(
	PNPM_STORE,
	"react@19.2.5",
	"node_modules",
	"react",
);
const REACT_DOM_19 = path.join(
	PNPM_STORE,
	"react-dom@19.2.5_react@19.2.5",
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
			// audit-2026 JS-03: explicit React 19 entrypoint for the contract test.
			react19: REACT_19,
			"react19-dom/client": path.join(REACT_DOM_19, "client.js"),
		},
	},
});
