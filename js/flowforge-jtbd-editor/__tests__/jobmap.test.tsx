import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JobMap } from "../src/JobMap.js";
import {
	FIRST_NODE_X,
	LANE_HEIGHT,
	NODE_WIDTH,
	NODE_X_GAP,
	NODE_Y_OFFSET,
	layoutJobMap,
} from "../src/layout.js";
import { sampleBundle } from "../src/fixtures.js";
import type { JtbdBundle } from "../src/types.js";

describe("layoutJobMap", () => {
	it("groups specs into one lane per actor role in first-appearance order", () => {
		const layout = layoutJobMap(sampleBundle());
		expect(layout.lanes.map((l) => l.role)).toEqual([
			"intake_clerk",
			"triage_officer",
			"claims_supervisor",
		]);
		expect(layout.lanes.map((l) => l.index)).toEqual([0, 1, 2]);
	});

	it("assigns topological columns based on requires depth", () => {
		const layout = layoutJobMap(sampleBundle());
		const byId = Object.fromEntries(
			layout.nodes.map((n) => [n.jtbdId, n.column]),
		);
		expect(byId.claim_intake).toBe(0);
		expect(byId.claim_triage).toBe(1);
		expect(byId.claim_assign).toBe(2);
		expect(byId.claim_approve).toBe(3);
	});

	it("places nodes at deterministic pixel positions", () => {
		const layout = layoutJobMap(sampleBundle());
		const intake = layout.nodes.find((n) => n.jtbdId === "claim_intake");
		expect(intake).toBeDefined();
		expect(intake?.x).toBe(FIRST_NODE_X);
		expect(intake?.y).toBe(0 * LANE_HEIGHT + NODE_Y_OFFSET);

		const triage = layout.nodes.find((n) => n.jtbdId === "claim_triage");
		expect(triage?.x).toBe(FIRST_NODE_X + 1 * (NODE_WIDTH + NODE_X_GAP));
		expect(triage?.y).toBe(1 * LANE_HEIGHT + NODE_Y_OFFSET);
	});

	it("flags cross-lane edges so the canvas can recolor them", () => {
		const layout = layoutJobMap(sampleBundle());
		const e = layout.edges.find((edge) => edge.id === "claim_intake->claim_triage");
		expect(e?.crossLane).toBe(true);

		const sameLane = layout.edges.find(
			(edge) => edge.id === "claim_triage->claim_assign",
		);
		expect(sameLane?.crossLane).toBe(false);
	});

	it("skips edges whose upstream is missing rather than throwing", () => {
		const bundle: JtbdBundle = {
			project: { name: "x", package: "x", domain: "y" },
			jtbds: [
				{
					id: "child",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
					requires: ["ghost"],
				},
			],
		};
		const layout = layoutJobMap(bundle);
		expect(layout.edges).toEqual([]);
	});

	it("marks every node in a cycle so the linter's hint can render", () => {
		const bundle: JtbdBundle = {
			project: { name: "x", package: "x", domain: "y" },
			jtbds: [
				{
					id: "a",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
					requires: ["b"],
				},
				{
					id: "b",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
					requires: ["a"],
				},
			],
		};
		const layout = layoutJobMap(bundle);
		const a = layout.nodes.find((n) => n.jtbdId === "a");
		const b = layout.nodes.find((n) => n.jtbdId === "b");
		expect(a?.inCycle).toBe(true);
		expect(b?.inCycle).toBe(true);
	});

	it("computes width + height that cover every laid-out node", () => {
		const layout = layoutJobMap(sampleBundle());
		const farthest = Math.max(...layout.nodes.map((n) => n.x + n.width));
		expect(layout.width).toBeGreaterThanOrEqual(farthest);
		expect(layout.height).toBe(3 * LANE_HEIGHT);
	});

	it("treats an empty bundle gracefully", () => {
		const layout = layoutJobMap({
			project: { name: "x", package: "x", domain: "y" },
			jtbds: [],
		});
		expect(layout.lanes).toEqual([]);
		expect(layout.nodes).toEqual([]);
		expect(layout.edges).toEqual([]);
		expect(layout.height).toBe(LANE_HEIGHT);
	});
});

describe("JobMap (SVG fallback)", () => {
	it("renders a region with one lane label per actor", () => {
		render(<JobMap bundle={sampleBundle()} withReactFlow={false} />);
		expect(screen.getByTestId("ff-jobmap")).toBeInTheDocument();
		expect(
			screen.getByTestId("ff-jobmap-lane-label-intake_clerk"),
		).toHaveTextContent("intake_clerk");
		expect(
			screen.getByTestId("ff-jobmap-lane-label-triage_officer"),
		).toHaveTextContent("triage_officer");
		expect(
			screen.getByTestId("ff-jobmap-lane-label-claims_supervisor"),
		).toHaveTextContent("claims_supervisor");
	});

	it("renders one node per JTBD with title + id", () => {
		render(<JobMap bundle={sampleBundle()} withReactFlow={false} />);
		const intake = screen.getByTestId("ff-jobmap-node-claim_intake");
		expect(intake).toBeInTheDocument();
		expect(intake).toHaveTextContent("Submit a new motor claim");
		expect(intake).toHaveTextContent("claim_intake");
		expect(intake.getAttribute("data-role")).toBe("intake_clerk");
		expect(intake.getAttribute("data-column")).toBe("0");
	});

	it("renders one edge per requires hop with the correct cross-lane flag", () => {
		render(<JobMap bundle={sampleBundle()} withReactFlow={false} />);
		const intakeToTriage = screen.getByTestId(
			"ff-jobmap-edge-claim_intake->claim_triage",
		);
		expect(intakeToTriage.getAttribute("data-crosslane")).toBe("true");

		const triageToAssign = screen.getByTestId(
			"ff-jobmap-edge-claim_triage->claim_assign",
		);
		expect(triageToAssign.getAttribute("data-crosslane")).toBe("false");
	});

	it("invokes onSelectJtbd when a node is clicked", () => {
		const onSelect = vi.fn();
		render(
			<JobMap
				bundle={sampleBundle()}
				withReactFlow={false}
				onSelectJtbd={onSelect}
			/>,
		);
		fireEvent.click(screen.getByTestId("ff-jobmap-node-claim_triage"));
		expect(onSelect).toHaveBeenCalledWith("claim_triage");
	});

	it("invokes onSelectJtbd when Enter is pressed for keyboard a11y", () => {
		const onSelect = vi.fn();
		render(
			<JobMap
				bundle={sampleBundle()}
				withReactFlow={false}
				onSelectJtbd={onSelect}
			/>,
		);
		const node = screen.getByTestId("ff-jobmap-node-claim_intake");
		fireEvent.keyDown(node, { key: "Enter" });
		expect(onSelect).toHaveBeenCalledWith("claim_intake");
	});

	it("marks nodes in a cycle via data-incycle for visual flag", () => {
		const cyclic: JtbdBundle = {
			project: { name: "x", package: "x", domain: "y" },
			jtbds: [
				{
					id: "a",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
					requires: ["b"],
				},
				{
					id: "b",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
					requires: ["a"],
				},
			],
		};
		render(<JobMap bundle={cyclic} withReactFlow={false} />);
		expect(
			screen.getByTestId("ff-jobmap-node-a").getAttribute("data-incycle"),
		).toBe("true");
		expect(
			screen.getByTestId("ff-jobmap-node-b").getAttribute("data-incycle"),
		).toBe("true");
	});

	it("renders an empty job map without errors when the bundle has no jtbds", () => {
		render(
			<JobMap
				bundle={{
					project: { name: "x", package: "x", domain: "y" },
					jtbds: [],
				}}
				withReactFlow={false}
			/>,
		);
		expect(screen.getByTestId("ff-jobmap")).toBeInTheDocument();
		expect(screen.queryByTestId(/^ff-jobmap-node-/)).toBeNull();
	});
});

describe("JobMap performance budget", () => {
	it("lays out a 200-JTBD bundle in under 100ms", () => {
		const big: JtbdBundle = {
			project: { name: "perf", package: "perf", domain: "x" },
			jtbds: Array.from({ length: 200 }, (_, i) => ({
				id: `jtbd_${i}`,
				actor: { role: `role_${i % 8}` },
				situation: "s",
				motivation: "m",
				outcome: "o",
				success_criteria: ["sc"],
				requires: i > 0 ? [`jtbd_${i - 1}`] : [],
			})),
		};
		const start = performance.now();
		const layout = layoutJobMap(big);
		const elapsed = performance.now() - start;
		expect(layout.nodes).toHaveLength(200);
		// Soft budget — keeps the layout pass well below the 60fps
		// frame budget called out in jtbd-editor-arch §17.
		expect(elapsed).toBeLessThan(100);
	});
});
