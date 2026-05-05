import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
	plugins: [react()],
	test: {
		globals: true,
		environment: "happy-dom",
		setupFiles: ["./__tests__/setup.ts"],
		include: ["__tests__/**/*.test.{ts,tsx}"],
	},
});
