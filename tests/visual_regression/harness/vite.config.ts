import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../..");

function generatedFrontendAlias(): Plugin {
	function resolveGeneratedImport(target: string): string {
		const candidates = [
			target,
			`${target}.tsx`,
			`${target}.ts`,
			`${target}.jsx`,
			`${target}.js`,
			path.join(target, "index.tsx"),
			path.join(target, "index.ts"),
			path.join(target, "index.jsx"),
			path.join(target, "index.js"),
		];
		return candidates.find((candidate) => existsSync(candidate)) ?? target;
	}

	return {
		name: "flowforge-generated-frontend-alias",
		resolveId(source, importer) {
			if (!source.startsWith("@/") || importer == null) {
				return null;
			}
			const normal = path.normalize(importer);
			const marker = `${path.sep}generated${path.sep}frontend${path.sep}src${path.sep}`;
			const idx = normal.indexOf(marker);
			if (idx === -1) {
				return null;
			}
			const srcRoot = normal.slice(0, idx + marker.length - 1);
			return resolveGeneratedImport(path.join(srcRoot, source.slice(2)));
		},
	};
}

export default defineConfig({
	root: __dirname,
	plugins: [generatedFrontendAlias(), react()],
	define: {
		"process.env.NEXT_PUBLIC_FLOWFORGE_API_BASE_URL": JSON.stringify(
			process.env.NEXT_PUBLIC_FLOWFORGE_API_BASE_URL ?? "",
		),
		"process.env.NEXT_PUBLIC_FLOWFORGE_DEMO_MODE": JSON.stringify(
			process.env.NEXT_PUBLIC_FLOWFORGE_DEMO_MODE ?? "",
		),
		"process.env.NEXT_PUBLIC_FLOWFORGE_TENANT_ID": JSON.stringify(
			process.env.NEXT_PUBLIC_FLOWFORGE_TENANT_ID ?? "",
		),
	},
	resolve: {
		alias: [
			{
				find: "@flowforge/renderer/styles.css",
				replacement: path.resolve(repoRoot, "js/flowforge-renderer/src/styles.css"),
			},
			{
				find: "@flowforge/renderer",
				replacement: path.resolve(repoRoot, "js/flowforge-renderer/src/index.ts"),
			},
			{
				find: "@flowforge/types",
				replacement: path.resolve(repoRoot, "js/flowforge-types/src/index.ts"),
			},
		],
	},
	server: {
		host: "127.0.0.1",
		fs: {
			allow: [repoRoot],
		},
	},
});
