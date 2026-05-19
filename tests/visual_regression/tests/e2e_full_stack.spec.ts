import { expect, test } from "@playwright/test";

import { EXAMPLES, harnessUrl, type PageSpec } from "../lib/page_catalog";

const DEV_SERVER_URL = (process.env.VISREG_DEV_SERVER_URL ?? "").replace(/\/$/, "");
const API_URL = (process.env.FLOWFORGE_BROWSER_E2E_API_URL ?? "").replace(/\/$/, "");
const REQUIRE_ENV = process.env.FLOWFORGE_BROWSER_E2E_REQUIRE === "1";
const TENANT_ID = "tenant-browser-e2e";
const INSTANCE_ID = "browser-e2e-instance-1";

function claimIntakePage(): PageSpec {
	const example = EXAMPLES.find((item) => item.name === "insurance_claim");
	const page = example?.pages.find(
		(item) => item.flavor === "frontend" && item.id === "claim-intake",
	);
	if (page == null) {
		throw new Error("insurance_claim claim-intake page missing from harness catalog");
	}
	return page;
}

test.describe("browser full-stack generated workflow", () => {
	const envReady = DEV_SERVER_URL.length > 0 && API_URL.length > 0;
	test.skip(!REQUIRE_ENV && !envReady, "browser full-stack e2e requires wrapper-provided dev-server and API URLs");

	test.beforeAll(() => {
		if (!envReady) {
			throw new Error(
				"missing VISREG_DEV_SERVER_URL or FLOWFORGE_BROWSER_E2E_API_URL; run scripts/run_browser_full_stack.sh",
			);
		}
	});

	test("generated frontend posts submit and approve through the generated FastAPI router", async ({
		page,
		request,
	}) => {
		const target = `${DEV_SERVER_URL}${harnessUrl(
			"insurance_claim",
			claimIntakePage(),
		)}?instance_id=${encodeURIComponent(INSTANCE_ID)}`;

		await page.goto(target);
		await expect(page.locator("main")).toHaveAttribute(
			"data-flowforge-runtime-mode",
			"api",
		);

		const form = page.getByTestId("claim_intake-form");
		await form.getByLabel("Claimant full name", { exact: true }).fill("Amina Diallo");
		await form.getByLabel("Policy number", { exact: true }).fill("POL-2026-0001");
		await form.getByLabel("Date of loss", { exact: true }).fill("2026-05-18");
		await form.getByLabel("Estimated loss amount", { exact: true }).fill("1250.00");
		await form
			.getByLabel("Description of loss")
			.fill("Rear bumper damage after a low-speed collision.");
		await form.getByLabel("Contact email", { exact: true }).fill("amina@example.test");
		await form.getByLabel("Contact phone", { exact: true }).fill("+1 555 0100");

		await page.getByRole("button", { name: "Submit" }).click();
		await expect.poll(async () => {
			const response = await request.get(
				`${API_URL}/__flowforge_browser_e2e/requests`,
			);
			const body = (await response.json()) as { requests: unknown[] };
			return body.requests.length;
		}).toBeGreaterThanOrEqual(1);

		await page.getByRole("button", { name: "Approve" }).click();
		await expect.poll(async () => {
			const response = await request.get(
				`${API_URL}/__flowforge_browser_e2e/requests`,
			);
			const body = (await response.json()) as { requests: unknown[] };
			return body.requests.length;
		}).toBeGreaterThanOrEqual(2);

		const response = await request.get(
			`${API_URL}/__flowforge_browser_e2e/requests`,
		);
		const body = (await response.json()) as {
			requests: Array<{
				headers: Record<string, string>;
				request_body: {
					event: string;
					instance_id: string;
					payload: Record<string, unknown>;
				};
				response_body: Record<string, unknown>;
				status_code: number;
			}>;
		};

		expect(body.requests).toHaveLength(2);
		const [submit, approve] = body.requests;
		expect(submit.status_code).toBe(200);
		expect(submit.headers["x-tenant-id"]).toBe(TENANT_ID);
		expect(submit.headers["idempotency-key"]).toContain(
			`claim-intake:${INSTANCE_ID}:submit:`,
		);
		expect(submit.request_body).toMatchObject({
			event: "submit",
			instance_id: INSTANCE_ID,
		});
		expect(submit.request_body.payload).toMatchObject({
			instance_id: INSTANCE_ID,
			policy_number: "POL-2026-0001",
		});
		expect(submit.response_body).toMatchObject({
			matched: true,
			state: "review",
		});

		expect(approve.status_code).toBe(200);
		expect(approve.headers["x-tenant-id"]).toBe(TENANT_ID);
		expect(approve.headers["idempotency-key"]).toContain(
			`claim-intake:${INSTANCE_ID}:approve:`,
		);
		expect(approve.request_body).toMatchObject({
			event: "approve",
			instance_id: INSTANCE_ID,
			payload: {},
		});
		expect(approve.response_body).toMatchObject({
			matched: true,
			state: "done",
		});
		await expect(page.getByRole("alert")).toHaveCount(0);
	});
});
