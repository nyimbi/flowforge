import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormRenderer } from "../src/FormRenderer.js";
import type { LookupRegistry, RendererFormSpec } from "../src/types.js";

function comprehensiveSpec(): RendererFormSpec {
	return {
		id: "everything",
		version: "1.0.0",
		title: "Everything form",
		fields: [
			{ id: "txt", kind: "text", label: "Name", required: true },
			{ id: "long", kind: "textarea", label: "Notes" },
			{ id: "rich", kind: "rich_text", label: "Body" },
			{ id: "n", kind: "number", label: "Count" },
			{ id: "money", kind: "money", label: "Amount", validation: { currency: "USD" } },
			{ id: "d", kind: "date", label: "Date" },
			{ id: "dt", kind: "datetime", label: "When" },
			{ id: "b", kind: "boolean", label: "Agree" },
			{
				id: "cat",
				kind: "enum",
				label: "Category",
				options: [
					{ v: "a", label: "A" },
					{ v: "b", label: "B" },
				],
			},
			{
				id: "tags",
				kind: "multi_select",
				label: "Tags",
				options: [{ v: "x" }, { v: "y" }, { v: "z" }],
			},
			{ id: "doc", kind: "file", label: "Doc" },
			{ id: "sig", kind: "signature", label: "Signature" },
			{ id: "rt", kind: "rich_text", label: "Rich" },
			{ id: "addr", kind: "address", label: "Address" },
			{ id: "phone", kind: "phone", label: "Phone" },
			{ id: "email", kind: "email", label: "Email" },
			{ id: "site", kind: "url", label: "Site" },
			{ id: "color", kind: "color", label: "Color" },
			{ id: "pct", kind: "percentage", label: "Pct" },
			{ id: "raw", kind: "json", label: "JSON" },
			{ id: "secret", kind: "hidden", default: "h1" },
			{ id: "party", kind: "party_picker", label: "Party", source: { hook: "parties" } },
			{ id: "doc_ref", kind: "document_picker", label: "Doc ref", source: { hook: "docs" } },
			{ id: "lk", kind: "lookup", label: "Lookup", source: { hook: "parties" } },
		],
	};
}

describe("FormRenderer", () => {
	it("renders every supported field kind", () => {
		render(<FormRenderer spec={comprehensiveSpec()} />);
		const expectedIds = [
			"txt", "long", "rich", "n", "money", "d", "dt", "b", "cat", "tags",
			"doc", "sig", "rt", "addr", "phone", "email", "site", "color", "pct",
			"raw", "secret", "party", "doc_ref", "lk",
		];
		for (const id of expectedIds) {
			expect(document.querySelector(`[data-flowforge-field="${id}"]`)).toBeTruthy();
		}
	});

	it("invokes onChange when user types", async () => {
		const handle = vi.fn();
		const user = userEvent.setup();
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [{ id: "n", kind: "text", label: "Name" }],
				}}
				onChange={handle}
			/>,
		);
		await user.type(screen.getByLabelText("Name"), "Ada");
		// onChange called per keystroke; final call has the full string.
		const last = handle.mock.calls.at(-1)?.[0];
		expect(last).toEqual({ n: "Ada" });
	});

	it("blocks submit when required fields are empty and surfaces errors", async () => {
		const onSubmit = vi.fn();
		const onValidate = vi.fn();
		const user = userEvent.setup();
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [
						{ id: "name", kind: "text", label: "Name", required: true },
						{ id: "email", kind: "email", label: "Email", required: true },
					],
				}}
				onSubmit={onSubmit}
				onValidate={onValidate}
			/>,
		);
		await user.click(screen.getByRole("button", { name: /submit/i }));
		expect(onSubmit).not.toHaveBeenCalled();
		expect(onValidate).toHaveBeenCalled();
		expect(screen.getAllByRole("alert")).not.toHaveLength(0);
	});

	it("submits when fields are valid", async () => {
		const onSubmit = vi.fn();
		const user = userEvent.setup();
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [{ id: "name", kind: "text", label: "Name", required: true }],
				}}
				onSubmit={onSubmit}
			/>,
		);
		await user.type(screen.getByLabelText("Name"), "Ada");
		await user.click(screen.getByRole("button", { name: /submit/i }));
		await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ name: "Ada" }));
	});

	it("hides fields whose visible_if is falsy", () => {
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [
						{ id: "kind", kind: "enum", label: "Kind", options: [{ v: "person" }, { v: "company" }] },
						{
							id: "tax_id",
							kind: "text",
							label: "Tax ID",
							visible_if: { "==": ["$.kind", "company"] },
						},
					],
				}}
			/>,
		);
		expect(screen.queryByLabelText("Tax ID")).toBeNull();
	});

	it("shows conditional fields when their guard becomes true", () => {
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [
						{ id: "kind", kind: "enum", label: "Kind", options: [{ v: "person" }, { v: "company" }] },
						{
							id: "tax_id",
							kind: "text",
							label: "Tax ID",
							visible_if: { "==": ["$.kind", "company"] },
						},
					],
				}}
				values={{ kind: "company" }}
			/>,
		);
		expect(screen.getByLabelText("Tax ID")).toBeTruthy();
	});

	it("computes computed fields from upstream values", async () => {
		const handle = vi.fn();
		const user = userEvent.setup();
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [
						{ id: "qty", kind: "number", label: "Qty", default: 0 },
						{ id: "price", kind: "number", label: "Price", default: 10 },
						{
							id: "total",
							kind: "number",
							label: "Total",
							computed: { expr: { "*": ["$.qty", "$.price"] } },
						},
					],
				}}
				onChange={handle}
			/>,
		);
		await user.clear(screen.getByLabelText("Qty"));
		await user.type(screen.getByLabelText("Qty"), "3");
		const last = handle.mock.calls.at(-1)?.[0];
		expect(last.total).toBe(30);
	});

	it("calls async lookup hook for lookup-kind fields", async () => {
		const lookups: LookupRegistry = {
			parties: vi.fn(async ({ query }) => [{ v: "p1", label: query ? `Party ${query}` : "Party 1" }]),
		};
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [{ id: "p", kind: "lookup", label: "Party", source: { hook: "parties" } }],
				}}
				lookups={lookups}
			/>,
		);
		await waitFor(() => {
			expect(lookups.parties).toHaveBeenCalled();
		});
	});

	it("renders fields grouped by layout sections", () => {
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [
						{ id: "a", kind: "text", label: "A" },
						{ id: "b", kind: "text", label: "B" },
					],
					layout: [
						{ kind: "section", title: "Section 1", field_ids: ["a"] },
						{ kind: "section", title: "Section 2", field_ids: ["b"] },
					],
				}}
			/>,
		);
		expect(screen.getByText("Section 1")).toBeTruthy();
		expect(screen.getByText("Section 2")).toBeTruthy();
	});

	it("disables a field when disabled_if is true", () => {
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [
						{ id: "lock", kind: "boolean", label: "Lock" },
						{
							id: "name",
							kind: "text",
							label: "Name",
							disabled_if: { "==": ["$.lock", true] },
						},
					],
				}}
				values={{ lock: true }}
			/>,
		);
		expect(screen.getByLabelText("Name")).toBeDisabled();
	});

	it("file field accepts a file change", () => {
		const handle = vi.fn();
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [{ id: "doc", kind: "file", label: "Doc" }],
				}}
				onChange={handle}
			/>,
		);
		const file = new File(["hi"], "hi.txt", { type: "text/plain" });
		const input = screen.getByLabelText("Doc") as HTMLInputElement;
		fireEvent.change(input, { target: { files: [file] } });
		const last = handle.mock.calls.at(-1)?.[0];
		expect(last.doc).toMatchObject({ name: "hi.txt", size: 2, type: "text/plain" });
	});

	it("multi_select toggles selections", async () => {
		const handle = vi.fn();
		const user = userEvent.setup();
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [
						{
							id: "tags",
							kind: "multi_select",
							label: "Tags",
							options: [{ v: "x" }, { v: "y" }, { v: "z" }],
						},
					],
				}}
				onChange={handle}
			/>,
		);
		await user.click(screen.getByLabelText("x"));
		await user.click(screen.getByLabelText("z"));
		const last = handle.mock.calls.at(-1)?.[0];
		expect(last.tags).toEqual(expect.arrayContaining(["x", "z"]));
	});

	it("json field surfaces parse errors inline", async () => {
		const user = userEvent.setup();
		render(
			<FormRenderer
				spec={{
					id: "x",
					version: "1.0.0",
					title: "x",
					fields: [{ id: "raw", kind: "json", label: "Raw" }],
				}}
			/>,
		);
		const ta = screen.getByLabelText("Raw");
		// `{` is a userEvent special key; escape with `{{`.
		await user.type(ta, "{{not-json");
		expect(screen.getByRole("alert").textContent).toMatch(/Invalid JSON/);
	});
});
