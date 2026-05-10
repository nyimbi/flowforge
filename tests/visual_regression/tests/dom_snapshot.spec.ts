/**
 * DOM-snapshot byte-equality test (CI-gating per ADR-001).
 *
 * For each (example, page, viewport) tuple in the catalog, the test:
 *   1. Mounts the generated page in a Playwright-controlled Chromium.
 *   2. Extracts the rendered DOM via ``document.documentElement.outerHTML``.
 *   3. Normalises the DOM bytes per ADR-001 (strip ``data-react-*``,
 *      collapse whitespace, sort class tokens, sort attributes).
 *   4. Compares the normalised bytes against the checked-in baseline at
 *      ``examples/<example>/screenshots/<flavor>/<page>.<viewport>.dom.html``.
 *
 * When invoked with ``UPDATE_BASELINES=1``, the test writes the
 * normalised bytes to disk instead of asserting equality. Use that
 * mode to refresh baselines after intentional template changes — the
 * resulting files are committed in the same PR.
 *
 * Cadence (per ADR-001 §"Per-PR smoke"):
 *   * Per-PR: smoke subset (canonical example only). Set
 *     ``VISREG_CADENCE=smoke`` to run only the canonical example.
 *   * Nightly: full suite across every example. Set
 *     ``VISREG_CADENCE=full`` (default) to run every example.
 */
import * as fs from "node:fs";
import * as path from "node:path";

import { test, expect } from "@playwright/test";

import { normaliseDom } from "../lib/dom_normalize";
import {
	EXAMPLES,
	VIEWPORTS,
	baselinePaths,
	selectExamples,
	type PageSpec,
	type ViewportSpec,
} from "../lib/page_catalog";

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const CADENCE = (process.env.VISREG_CADENCE ?? "full") as "smoke" | "full";
const UPDATE_BASELINES = process.env.UPDATE_BASELINES === "1";
const DEV_SERVER_BASE = process.env.VISREG_DEV_SERVER_URL ?? "";

type Test = typeof test;

function describePage(
	t: Test,
	exampleName: string,
	page: PageSpec,
	viewport: ViewportSpec,
): void {
	const baselineRel = baselinePaths(exampleName, page, viewport.name).dom;
	const baselineAbs = path.join(REPO_ROOT, baselineRel);
	const entryAbs = path.join(REPO_ROOT, page.entry);
	const testTitle = `[dom] ${exampleName}/${page.flavor}/${page.id}@${viewport.name}`;

	t(testTitle, async ({ page: pwPage }, testInfo) => {
		// 1. Skip cleanly when the entry file is missing — happens on
		//    --form-renderer skeleton regen (no real Step.tsx emitted).
		if (!fs.existsSync(entryAbs)) {
			testInfo.skip(true, `entry missing (${page.entry}); likely skeleton regen`);
			return;
		}
		// 2. Skip cleanly when no dev server is wired. ADR-001 / W3 brief:
		//    the harness lands in the follow-up PR once `pnpm install` is
		//    unblocked. Until then, the gate skip-with-clear-reason rather
		//    than failing CI.
		if (!DEV_SERVER_BASE) {
			testInfo.skip(
				true,
				"VISREG_DEV_SERVER_URL not set; dev-server harness deferred until pnpm install is unblocked (see tests/visual_regression/README.md)",
			);
			return;
		}
		await pwPage.setViewportSize({
			width: viewport.width,
			height: viewport.height,
		});
		const url = new URL(page.url, DEV_SERVER_BASE).toString();
		await pwPage.goto(url, { waitUntil: "networkidle" });
		if (page.waitFor) {
			await pwPage.waitForSelector(page.waitFor, { state: "attached" });
		}
		const raw = await pwPage.evaluate(
			() => document.documentElement.outerHTML,
		);
		const normalised = normaliseDom(raw);

		if (UPDATE_BASELINES) {
			fs.mkdirSync(path.dirname(baselineAbs), { recursive: true });
			fs.writeFileSync(baselineAbs, normalised, "utf8");
			testInfo.annotations.push({
				type: "baseline",
				description: `wrote baseline: ${baselineRel}`,
			});
			return;
		}

		if (!fs.existsSync(baselineAbs)) {
			throw new Error(
				`missing DOM baseline: ${baselineRel}. Run ` +
					`\`pnpm --filter @flowforge/visual-regression update-baselines\` to seed it.`,
			);
		}
		const baseline = fs.readFileSync(baselineAbs, "utf8");
		// CI-gating byte equality — ADR-001 §"Decision".
		expect(normalised).toBe(baseline);
	});
}

const examples = selectExamples(CADENCE);
for (const example of examples) {
	test.describe(`example: ${example.name}`, () => {
		for (const pg of example.pages) {
			for (const vp of VIEWPORTS) {
				describePage(test, example.name, pg, vp);
			}
		}
	});
}

// Sanity check: the catalog must include every checked-in example.
test.describe("@meta", () => {
	test("[meta] catalog covers every example", () => {
		const present = new Set(EXAMPLES.map((e) => e.name));
		const checkedIn = fs
			.readdirSync(path.join(REPO_ROOT, "examples"))
			.filter((d) => fs.existsSync(path.join(REPO_ROOT, "examples", d, "jtbd-bundle.json")));
		const missing = checkedIn.filter((d) => !present.has(d));
		expect(missing).toEqual([]);
	});
});
