import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JtbdEditor, validateJtbdBundle } from "../src/Editor.js";
import { sampleBundle } from "../src/fixtures.js";
import type { JtbdBundle } from "../src/types.js";

const editableBundle = (): JtbdBundle => {
	const bundle = sampleBundle();
	return {
		...bundle,
		jtbds: bundle.jtbds.map((spec) => ({
			...spec,
			version: "1.0.0",
			domain: bundle.project.domain,
			description: `${spec.title ?? spec.id} description`,
			data_sensitivity: ["internal"],
		})),
	};
};

describe("JtbdEditor authoring", () => {
	it("opens a metadata panel for a clicked job and writes edited fields", async () => {
		const onChange = vi.fn<(bundle: JtbdBundle) => void>();
		render(
			<JtbdEditor
				bundle={editableBundle()}
				onChange={onChange}
				withReactFlow={false}
			/>,
		);

		fireEvent.click(await screen.findByTestId("ff-jobmap-node-claim_intake"));
		expect(screen.getByLabelText("JTBD metadata editor")).toBeInTheDocument();

		fireEvent.change(screen.getByLabelText("Title"), {
			target: { value: "Updated claim intake" },
		});
		expect(onChange.mock.lastCall?.[0].jtbds[0]?.title).toBe(
			"Updated claim intake",
		);

		fireEvent.change(screen.getByLabelText("Actors"), {
			target: { value: "broker, adjuster" },
		});
		const actorBundle = onChange.mock.lastCall?.[0];
		expect(actorBundle?.jtbds[0]?.actors).toEqual(["broker", "adjuster"]);
		expect(actorBundle?.jtbds[0]?.actor.role).toBe("broker");

		fireEvent.change(screen.getByLabelText("DataSensitivity"), {
			target: { value: "restricted" },
		});
		expect(onChange.mock.lastCall?.[0].jtbds[0]?.data_sensitivity).toEqual([
			"restricted",
		]);

		fireEvent.change(screen.getByLabelText("Version"), {
			target: { value: "not-semver" },
		});
		expect(await screen.findByText("Use semver, for example 1.0.0")).toBeInTheDocument();
	});

	it("opens a dependency editor for a clicked edge and stores edge metadata", async () => {
		const onChange = vi.fn<(bundle: JtbdBundle) => void>();
		render(
			<JtbdEditor
				bundle={editableBundle()}
				onChange={onChange}
				withReactFlow={false}
			/>,
		);

		fireEvent.click(
			await screen.findByTestId("ff-jobmap-edge-claim_intake->claim_triage"),
		);
		expect(screen.getByLabelText("Dependency editor")).toBeInTheDocument();

		fireEvent.change(screen.getByLabelText("Dependency type"), {
			target: { value: "blocks" },
		});
		fireEvent.change(screen.getByLabelText("Strength"), {
			target: { value: "optional" },
		});
		fireEvent.change(screen.getByLabelText("Description"), {
			target: { value: "Only needed for high-risk claims" },
		});

		const target = onChange.mock.lastCall?.[0].jtbds.find(
			(spec) => spec.id === "claim_triage",
		);
		expect(target?.dependencies).toEqual([
			{
				source: "claim_intake",
				type: "blocks",
				strength: "optional",
				description: "Only needed for high-risk claims",
			},
		]);
		expect(target?.requires).toContain("claim_intake");
	});

	it("shows validation issues and selects the affected node when an issue is clicked", async () => {
		const bundle = editableBundle();
		bundle.jtbds[0] = {
			...bundle.jtbds[0],
			version: "invalid",
		};
		render(<JtbdEditor bundle={bundle} withReactFlow={false} />);

		const node = await screen.findByTestId("ff-jobmap-node-claim_intake");
		expect(node.getAttribute("data-selected")).toBe("false");

		const issueText = await screen.findByText(
			"Submit a new motor claim has an invalid semver version",
		);
		const issueButton = issueText.closest("button");
		expect(issueButton).not.toBeNull();
		fireEvent.click(issueButton as HTMLButtonElement);

		expect(screen.getByTestId("ff-jobmap-node-claim_intake")).toHaveAttribute(
			"data-selected",
			"true",
		);
	});

	it("shows a green validation banner when the bundle has no issues", () => {
		expect(validateJtbdBundle(editableBundle())).toEqual([]);
		render(<JtbdEditor bundle={editableBundle()} withReactFlow={false} />);
		expect(screen.getByText("✓ No validation issues")).toBeInTheDocument();
	});

	it("exports the current bundle as downloaded JSON", () => {
		const createObjectURL = vi.fn(() => "blob:jtbd");
		const revokeObjectURL = vi.fn();
		const click = vi.fn();
		const originalCreateObjectURL = URL.createObjectURL;
		const originalRevokeObjectURL = URL.revokeObjectURL;
		const originalClick = HTMLAnchorElement.prototype.click;
		Object.defineProperty(URL, "createObjectURL", {
			configurable: true,
			value: createObjectURL,
		});
		Object.defineProperty(URL, "revokeObjectURL", {
			configurable: true,
			value: revokeObjectURL,
		});
		Object.defineProperty(HTMLAnchorElement.prototype, "click", {
			configurable: true,
			value: click,
		});

		try {
			render(<JtbdEditor bundle={editableBundle()} withReactFlow={false} />);
			fireEvent.click(screen.getByText("Export JSON"));

			expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
			expect(click).toHaveBeenCalled();
			expect(revokeObjectURL).toHaveBeenCalledWith("blob:jtbd");
		} finally {
			Object.defineProperty(URL, "createObjectURL", {
				configurable: true,
				value: originalCreateObjectURL,
			});
			Object.defineProperty(URL, "revokeObjectURL", {
				configurable: true,
				value: originalRevokeObjectURL,
			});
			Object.defineProperty(HTMLAnchorElement.prototype, "click", {
				configurable: true,
				value: originalClick,
			});
		}
	});

	it("shows an empty state and can add the first job", async () => {
		const onChange = vi.fn<(bundle: JtbdBundle) => void>();
		render(
			<JtbdEditor
				bundle={{
					project: { name: "empty", package: "empty", domain: "general" },
					jtbds: [],
				}}
				onChange={onChange}
				withReactFlow={false}
			/>,
		);

		expect(await screen.findByText("No jobs defined yet")).toBeInTheDocument();
		const addButtons = screen.getAllByText("+ Add Job");
		fireEvent.click(addButtons[addButtons.length - 1] as HTMLElement);

		expect(onChange.mock.lastCall?.[0].jtbds).toHaveLength(1);
		expect(onChange.mock.lastCall?.[0].jtbds[0]?.id).toBe("job_1");
	});
});
