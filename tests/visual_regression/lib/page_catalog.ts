/**
 * Page catalog for the visual regression suite.
 *
 * Enumerates every (example, frontend-flavor, page, viewport) tuple that
 * the runner mounts and snapshots. The catalog is hand-maintained so the
 * suite stays deterministic across regenerations — the generator may
 * reorder its own `app/` directory but our coverage list is pinned.
 *
 * Per ADR-001, baselines live at:
 *   examples/<example>/screenshots/<flavor>/<page>.<viewport>.{dom.html,png}
 *
 * Adding a new example or page: extend `EXAMPLES` below, then run
 *   `pnpm --filter @flowforge/visual-regression update-baselines`
 * which regenerates the baseline files and stages them for commit.
 */

export type FrontendFlavor = "frontend" | "frontend-admin";

export type ViewportName = "mobile" | "tablet" | "desktop";

export interface ViewportSpec {
	readonly name: ViewportName;
	readonly width: number;
	readonly height: number;
	readonly deviceScaleFactor: number;
}

export const VIEWPORTS: readonly ViewportSpec[] = [
	{ name: "mobile", width: 375, height: 667, deviceScaleFactor: 1 },
	{ name: "tablet", width: 768, height: 1024, deviceScaleFactor: 1 },
	{ name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1 },
] as const;

export interface PageSpec {
	/** Slug under `examples/<example>/screenshots/<flavor>/`. */
	readonly id: string;
	/** Frontend flavor: real-path Step.tsx (`frontend`) or admin SPA (`frontend-admin`). */
	readonly flavor: FrontendFlavor;
	/**
	 * Path to the entry-point file (relative to repo root). Used to skip
	 * the test cleanly when the file is missing — keeps the suite green
	 * across `--form-renderer skeleton` regen runs that don't emit a
	 * real Step.tsx.
	 */
	readonly entry: string;
	/**
	 * URL the runner navigates to once the dev server is up. The dev
	 * server is configured per-flavor in `playwright.config.ts`.
	 */
	readonly url: string;
	/**
	 * Optional CSS selector to wait for before snapshotting. Defaults to
	 * `body` (i.e. document is ready). Step pages override to wait for
	 * the form root.
	 */
	readonly waitFor?: string;
}

export interface ExampleSpec {
	readonly name: string;
	readonly pages: readonly PageSpec[];
}

/**
 * Per-example page catalog. The canonical example for the per-PR DOM
 * smoke is `insurance_claim` (per ADR-001 §"Per-PR smoke"). The other
 * examples run only in the nightly full-suite.
 */
export const EXAMPLES: readonly ExampleSpec[] = [
	{
		name: "insurance_claim",
		pages: [
			{
				id: "claim-intake",
				flavor: "frontend",
				entry:
					"examples/insurance_claim/generated/frontend/src/app/claim-intake/page.tsx",
				url: "/claim-intake",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "audit-log-viewer",
				flavor: "frontend-admin",
				entry:
					"examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/AuditLogViewer.tsx",
				url: "/audit",
			},
			{
				id: "instance-browser",
				flavor: "frontend-admin",
				entry:
					"examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/InstanceBrowser.tsx",
				url: "/instances",
			},
			{
				id: "outbox-queue",
				flavor: "frontend-admin",
				entry:
					"examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/OutboxQueue.tsx",
				url: "/outbox",
			},
			{
				id: "rls-log",
				flavor: "frontend-admin",
				entry:
					"examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/RlsLog.tsx",
				url: "/rls",
			},
			{
				id: "saga-panel",
				flavor: "frontend-admin",
				entry:
					"examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/SagaPanel.tsx",
				url: "/saga",
			},
			{
				id: "permissions-history",
				flavor: "frontend-admin",
				entry:
					"examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/PermissionsHistory.tsx",
				url: "/permissions",
			},
		],
	},
	{
		name: "building-permit",
		pages: [
			{
				id: "permit-intake",
				flavor: "frontend",
				entry:
					"examples/building-permit/generated/frontend/src/app/permit-intake/page.tsx",
				url: "/permit-intake",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "plan-review",
				flavor: "frontend",
				entry:
					"examples/building-permit/generated/frontend/src/app/plan-review/page.tsx",
				url: "/plan-review",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "field-inspection",
				flavor: "frontend",
				entry:
					"examples/building-permit/generated/frontend/src/app/field-inspection/page.tsx",
				url: "/field-inspection",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "permit-decision",
				flavor: "frontend",
				entry:
					"examples/building-permit/generated/frontend/src/app/permit-decision/page.tsx",
				url: "/permit-decision",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "permit-issuance",
				flavor: "frontend",
				entry:
					"examples/building-permit/generated/frontend/src/app/permit-issuance/page.tsx",
				url: "/permit-issuance",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "audit-log-viewer",
				flavor: "frontend-admin",
				entry:
					"examples/building-permit/generated/frontend-admin/building_permit/src/pages/AuditLogViewer.tsx",
				url: "/audit",
			},
			{
				id: "instance-browser",
				flavor: "frontend-admin",
				entry:
					"examples/building-permit/generated/frontend-admin/building_permit/src/pages/InstanceBrowser.tsx",
				url: "/instances",
			},
			{
				id: "outbox-queue",
				flavor: "frontend-admin",
				entry:
					"examples/building-permit/generated/frontend-admin/building_permit/src/pages/OutboxQueue.tsx",
				url: "/outbox",
			},
			{
				id: "rls-log",
				flavor: "frontend-admin",
				entry:
					"examples/building-permit/generated/frontend-admin/building_permit/src/pages/RlsLog.tsx",
				url: "/rls",
			},
			{
				id: "saga-panel",
				flavor: "frontend-admin",
				entry:
					"examples/building-permit/generated/frontend-admin/building_permit/src/pages/SagaPanel.tsx",
				url: "/saga",
			},
			{
				id: "permissions-history",
				flavor: "frontend-admin",
				entry:
					"examples/building-permit/generated/frontend-admin/building_permit/src/pages/PermissionsHistory.tsx",
				url: "/permissions",
			},
		],
	},
	{
		name: "hiring-pipeline",
		pages: [
			{
				id: "source-candidate",
				flavor: "frontend",
				entry:
					"examples/hiring-pipeline/generated/frontend/src/app/source-candidate/page.tsx",
				url: "/source-candidate",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "screen-candidate",
				flavor: "frontend",
				entry:
					"examples/hiring-pipeline/generated/frontend/src/app/screen-candidate/page.tsx",
				url: "/screen-candidate",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "conduct-interview",
				flavor: "frontend",
				entry:
					"examples/hiring-pipeline/generated/frontend/src/app/conduct-interview/page.tsx",
				url: "/conduct-interview",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "extend-offer",
				flavor: "frontend",
				entry:
					"examples/hiring-pipeline/generated/frontend/src/app/extend-offer/page.tsx",
				url: "/extend-offer",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "complete-hire",
				flavor: "frontend",
				entry:
					"examples/hiring-pipeline/generated/frontend/src/app/complete-hire/page.tsx",
				url: "/complete-hire",
				waitFor: "[data-flowforge-form-root]",
			},
			{
				id: "audit-log-viewer",
				flavor: "frontend-admin",
				entry:
					"examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/src/pages/AuditLogViewer.tsx",
				url: "/audit",
			},
			{
				id: "instance-browser",
				flavor: "frontend-admin",
				entry:
					"examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/src/pages/InstanceBrowser.tsx",
				url: "/instances",
			},
			{
				id: "outbox-queue",
				flavor: "frontend-admin",
				entry:
					"examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/src/pages/OutboxQueue.tsx",
				url: "/outbox",
			},
			{
				id: "rls-log",
				flavor: "frontend-admin",
				entry:
					"examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/src/pages/RlsLog.tsx",
				url: "/rls",
			},
			{
				id: "saga-panel",
				flavor: "frontend-admin",
				entry:
					"examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/src/pages/SagaPanel.tsx",
				url: "/saga",
			},
			{
				id: "permissions-history",
				flavor: "frontend-admin",
				entry:
					"examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/src/pages/PermissionsHistory.tsx",
				url: "/permissions",
			},
		],
	},
] as const;

/** Canonical example for the per-PR DOM smoke (per ADR-001 §"Per-PR smoke"). */
export const SMOKE_EXAMPLE = "insurance_claim";

/**
 * Returns the subset of examples to run for the requested cadence.
 * - ``"smoke"`` (per-PR): only the canonical example, DOM-snapshot only.
 * - ``"full"`` (nightly): every example.
 */
export function selectExamples(
	cadence: "smoke" | "full",
): readonly ExampleSpec[] {
	if (cadence === "smoke") {
		return EXAMPLES.filter((e) => e.name === SMOKE_EXAMPLE);
	}
	return EXAMPLES;
}

export interface BaselinePaths {
	readonly dom: string;
	readonly png: string;
}

/**
 * Returns the on-disk paths for a (example, page, viewport) baseline.
 * Caller resolves against the repo root.
 */
export function baselinePaths(
	exampleName: string,
	page: PageSpec,
	viewport: ViewportName,
): BaselinePaths {
	const dir = `examples/${exampleName}/screenshots/${page.flavor}`;
	return {
		dom: `${dir}/${page.id}.${viewport}.dom.html`,
		png: `${dir}/${page.id}.${viewport}.png`,
	};
}
