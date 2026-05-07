/**
 * audit-2026 E-66 / JS-08 ratchet — every workspace package keeps
 * ``"private": true`` so an accidental ``npm publish`` can't leak the
 * non-public flowforge JS code to the registry.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const JS_ROOT = path.resolve(HERE, "..");

function readPackage(filepath: string): { name?: string; private?: boolean } {
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
});
