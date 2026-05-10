/**
 * Pixel SSIM advisory test (nightly only per ADR-001).
 *
 * For each (example, page, viewport) tuple the test:
 *   1. Mounts the generated page in a Playwright-controlled Chromium.
 *   2. Captures a full-page PNG.
 *   3. Loads the baseline PNG at
 *      ``examples/<example>/screenshots/<flavor>/<page>.<viewport>.png``.
 *   4. Computes a windowed mean-similarity score (SSIM-like) between
 *      the candidate and baseline.
 *   5. Reports score ≥ 0.98 as PASS, < 0.98 as ADVISORY-FAIL.
 *
 * The advisory failure is annotated on the test result and reported in
 * the nightly summary. It does NOT block PR merge per ADR-001 §"Decision".
 *
 * When invoked with ``UPDATE_BASELINES=1``, the test writes the candidate
 * PNG to disk instead of asserting similarity.
 *
 * The pixel suite never runs per-PR. ADR-001 §"Decision" pins this
 * cadence: pixel bytes are not deterministic across Chromium minor
 * versions, so a per-PR pixel gate would produce false positives on
 * runner-image updates.
 */
import * as fs from "node:fs";
import * as path from "node:path";

import { test, expect } from "@playwright/test";

import { computeSsim, SSIM_THRESHOLD } from "../lib/ssim";
import {
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

function describePixel(
	t: Test,
	exampleName: string,
	page: PageSpec,
	viewport: ViewportSpec,
): void {
	const baselineRel = baselinePaths(exampleName, page, viewport.name).png;
	const baselineAbs = path.join(REPO_ROOT, baselineRel);
	const entryAbs = path.join(REPO_ROOT, page.entry);
	const testTitle = `[ssim] ${exampleName}/${page.flavor}/${page.id}@${viewport.name}`;

	t(testTitle, async ({ page: pwPage }, testInfo) => {
		if (!fs.existsSync(entryAbs)) {
			testInfo.skip(true, `entry missing (${page.entry}); likely skeleton regen`);
			return;
		}
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
		const candidatePng = await pwPage.screenshot({ fullPage: true, type: "png" });

		if (UPDATE_BASELINES) {
			fs.mkdirSync(path.dirname(baselineAbs), { recursive: true });
			fs.writeFileSync(baselineAbs, candidatePng);
			testInfo.annotations.push({
				type: "baseline",
				description: `wrote pixel baseline: ${baselineRel}`,
			});
			return;
		}

		if (!fs.existsSync(baselineAbs)) {
			// Advisory: missing baseline is annotated but does not fail the
			// suite. Nightly summary surfaces these as new pages awaiting
			// baseline review.
			testInfo.annotations.push({
				type: "advisory:missing-baseline",
				description: `missing pixel baseline: ${baselineRel}`,
			});
			testInfo.skip(true, "missing pixel baseline (advisory; not a CI gate)");
			return;
		}
		const baseline = fs.readFileSync(baselineAbs);
		const outcome = await computeSsim(
			new Uint8Array(baseline.buffer, baseline.byteOffset, baseline.byteLength),
			new Uint8Array(candidatePng.buffer, candidatePng.byteOffset, candidatePng.byteLength),
		);
		if (outcome.status === "unavailable") {
			testInfo.skip(true, `SSIM unavailable: ${outcome.reason}`);
			return;
		}
		if (outcome.status === "size-mismatch") {
			testInfo.annotations.push({
				type: "advisory:size-mismatch",
				description: outcome.reason,
			});
			testInfo.skip(true, `SSIM size mismatch (advisory): ${outcome.reason}`);
			return;
		}
		const { score, width, height } = outcome.result;
		testInfo.annotations.push({
			type: "ssim",
			description: `score=${score.toFixed(4)} (${width}x${height}, threshold=${SSIM_THRESHOLD})`,
		});
		// The advisory gate "passes" when score >= threshold; otherwise we
		// annotate the result but DO NOT throw. Nightly summary picks up
		// the annotation and posts a PR comment per ADR-001 §"Decision".
		if (score < SSIM_THRESHOLD) {
			testInfo.annotations.push({
				type: "advisory:ssim-below-threshold",
				description: `SSIM ${score.toFixed(4)} < ${SSIM_THRESHOLD} for ${baselineRel}`,
			});
		}
		// expect() asserts the score is at least the threshold. The
		// `audit-2026-visual-regression-ssim` Make target wraps this with
		// `|| true` so the advisory failure shows up in the report
		// without breaking the build.
		expect(score).toBeGreaterThanOrEqual(SSIM_THRESHOLD);
	});
}

const examples = selectExamples(CADENCE);
for (const example of examples) {
	test.describe(`example: ${example.name}`, () => {
		for (const pg of example.pages) {
			for (const vp of VIEWPORTS) {
				describePixel(test, example.name, pg, vp);
			}
		}
	});
}
