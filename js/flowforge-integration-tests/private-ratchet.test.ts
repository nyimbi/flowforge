/**
 * audit-2026 E-66 / JS-08 ratchet — every workspace package keeps
 * ``"private": true`` so an accidental ``npm publish`` can't leak the
 * non-public flowforge JS code to the registry.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const JS_ROOT = path.resolve(HERE, "..");

type PackageJson = {
	name?: string;
	private?: boolean;
	main?: unknown;
	scripts?: Record<string, unknown>;
	types?: unknown;
	exports?: unknown;
	publishConfig?: unknown;
};

function readPackage(filepath: string): PackageJson {
	return JSON.parse(readFileSync(filepath, "utf-8"));
}

function workspacePackageJsons(): string[] {
	const out: string[] = [];
	// Root workspace package.
	out.push(path.join(JS_ROOT, "package.json"));
	// Each `flowforge-*` package.
	for (const entry of readdirSync(JS_ROOT)) {
		if (!entry.startsWith("flowforge-")) continue;
		const subdir = path.join(JS_ROOT, entry);
		try {
			if (!statSync(subdir).isDirectory()) continue;
		} catch {
			continue;
		}
		const pj = path.join(subdir, "package.json");
		try {
			statSync(pj);
		} catch {
			continue;
		}
		out.push(pj);
	}
	return out;
}

function referencesTsSource(value: unknown): boolean {
	if (typeof value === "string") {
		return (
			value.startsWith("src/")
			|| value.startsWith("./src/")
			|| value.includes("/src/")
		) && (value.endsWith(".ts") || value.endsWith(".tsx"));
	}
	if (Array.isArray(value)) {
		return value.some((item) => referencesTsSource(item));
	}
	if (value !== null && typeof value === "object") {
		return Object.values(value).some((item) => referencesTsSource(item));
	}
	return false;
}

function collectRelativePackagePaths(value: unknown, out: Set<string>): void {
	if (typeof value === "string") {
		if (value.startsWith("./") || value.startsWith("src/")) {
			out.add(value.replace(/^\.\//, ""));
		}
		return;
	}
	if (Array.isArray(value)) {
		for (const item of value) collectRelativePackagePaths(item, out);
		return;
	}
	if (value !== null && typeof value === "object") {
		for (const item of Object.values(value)) collectRelativePackagePaths(item, out);
	}
}

function npmPackDryRunFiles(packageDir: string): Set<string> {
	const output = execFileSync("npm", ["pack", "--dry-run", "--json"], {
		cwd: packageDir,
		encoding: "utf-8",
		env: {
			...process.env,
			NPM_CONFIG_CACHE:
				process.env.NPM_CONFIG_CACHE
				?? path.join(tmpdir(), "flowforge-npm-cache"),
		},
	});
	const parsed = JSON.parse(output) as Array<{ files: Array<{ path: string }> }>;
	return new Set(parsed[0]?.files.map((file) => file.path) ?? []);
}

describe("test_JS_08_integration_private", () => {
	it("every flowforge JS workspace package is marked private", () => {
		const offenders: string[] = [];
		for (const pj of workspacePackageJsons()) {
			const pkg = readPackage(pj);
			if (pkg.private !== true) {
				offenders.push(`${pkg.name ?? pj}: private != true`);
			}
		}
		expect(offenders).toEqual([]);
	});

	it("flowforge-integration-tests is private", () => {
		const pj = path.join(JS_ROOT, "flowforge-integration-tests", "package.json");
		const pkg = readPackage(pj);
		expect(pkg.private).toBe(true);
		expect(pkg.name).toBe("@flowforge/integration-tests");
	});

	it("source-first TypeScript entrypoints are private-only", () => {
		const offenders: string[] = [];
		for (const pj of workspacePackageJsons()) {
			const pkg = readPackage(pj);
			const sourceFirst = referencesTsSource(pkg.main)
				|| referencesTsSource(pkg.types)
				|| referencesTsSource(pkg.exports);
			if (!sourceFirst) continue;
			if (pkg.private !== true) {
				offenders.push(`${pkg.name ?? pj}: source-first export without private=true`);
			}
			if (pkg.publishConfig !== undefined) {
				offenders.push(`${pkg.name ?? pj}: source-first export has publishConfig`);
			}
		}
		expect(offenders).toEqual([]);
	});

	it("workspace lint scripts are real static checks, not placeholders", () => {
		const offenders: string[] = [];
		for (const pj of workspacePackageJsons()) {
			const pkg = readPackage(pj);
			const lint = pkg.scripts?.lint;
			if (typeof lint !== "string") {
				offenders.push(`${pkg.name ?? pj}: missing lint script`);
				continue;
			}
			const packageDir = path.dirname(pj);
			if (packageDir === JS_ROOT) {
				if (lint !== "pnpm -r lint") {
					offenders.push(`${pkg.name ?? pj}: root lint must run pnpm -r lint`);
				}
				continue;
			}
			if (/\becho\b|\bexit\s+0\b|\btrue\b|no lint/i.test(lint)) {
				offenders.push(`${pkg.name ?? pj}: placeholder lint script ${JSON.stringify(lint)}`);
			}
			if (!/\b(tsc|eslint|biome|prettier|oxlint)\b/.test(lint)) {
				offenders.push(`${pkg.name ?? pj}: lint script is not a recognized static check`);
			}
		}
		expect(offenders).toEqual([]);
	});

	it("workspace build scripts are real static checks, not placeholders", () => {
		const offenders: string[] = [];
		for (const pj of workspacePackageJsons()) {
			const pkg = readPackage(pj);
			const build = pkg.scripts?.build;
			if (typeof build !== "string") {
				offenders.push(`${pkg.name ?? pj}: missing build script`);
				continue;
			}
			const packageDir = path.dirname(pj);
			if (packageDir === JS_ROOT) {
				if (build !== "pnpm -r build") {
					offenders.push(`${pkg.name ?? pj}: root build must run pnpm -r build`);
				}
				continue;
			}
			if (/\becho\b|\bexit\s+0\b|\btrue\b|no build/i.test(build)) {
				offenders.push(`${pkg.name ?? pj}: placeholder build script ${JSON.stringify(build)}`);
			}
			if (!/\b(tsc|vite|rollup|tsup|unbuild)\b/.test(build)) {
				offenders.push(`${pkg.name ?? pj}: build script is not a recognized static/build check`);
			}
		}
		expect(offenders).toEqual([]);
	});

	it("renderer ships its baseline stylesheet as a package export", () => {
		const packageDir = path.join(JS_ROOT, "flowforge-renderer");
		const pkg = readPackage(path.join(packageDir, "package.json"));
		expect(pkg.exports).toMatchObject({
			"./styles.css": "./src/styles.css",
		});
		const css = readFileSync(path.join(packageDir, "src", "styles.css"), "utf-8");
		for (const selector of [
			".ff-form",
			".ff-section",
			".ff-field",
			".ff-input",
			".ff-button--primary",
		]) {
			expect(css).toContain(selector);
		}
	});

	it("private source-first package tarballs contain their declared entrypoints", () => {
		const offenders: string[] = [];
		for (const pj of workspacePackageJsons()) {
			const packageDir = path.dirname(pj);
			if (packageDir === JS_ROOT) continue;
			const pkg = readPackage(pj);
			if (pkg.name === "@flowforge/integration-tests") continue;

			const requiredPaths = new Set<string>(["package.json"]);
			collectRelativePackagePaths(pkg.main, requiredPaths);
			collectRelativePackagePaths(pkg.types, requiredPaths);
			collectRelativePackagePaths(pkg.exports, requiredPaths);
			const packedFiles = npmPackDryRunFiles(packageDir);
			for (const requiredPath of requiredPaths) {
				if (!packedFiles.has(requiredPath)) {
					offenders.push(`${pkg.name ?? pj}: packed tarball missing ${requiredPath}`);
				}
			}
		}
		expect(offenders).toEqual([]);
	});
});
