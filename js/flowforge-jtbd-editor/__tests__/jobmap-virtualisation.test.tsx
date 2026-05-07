/**
 * E-67 / JS-07 — viewport virtualisation for large jobmaps.
 *
 * At 200+ JTBDs only viewport-visible nodes render. The pure helper
 * functions (`nodesInViewport`, `edgesInViewport`) are unit-tested
 * directly so the rendering path stays fast even when happy-dom
 * doesn't lay out elements.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
	JobMap,
	VIRTUALISATION_THRESHOLD,
	edgesInViewport,
	nodesInViewport,
	type JobMapViewport,
} from "../src/JobMap.js";
import {
	FIRST_NODE_X,
	LANE_HEIGHT,
	NODE_HEIGHT,
	NODE_WIDTH,
	NODE_X_GAP,
	NODE_Y_OFFSET,
	type EdgeLayout,
	type NodeLayout,
} from "../src/layout.js";
import type { JtbdBundle, JtbdSpec } from "../src/types.js";

const _node = (id: string, column: number, lane: number): NodeLayout => ({
	jtbdId: id,
	title: id,
	role: `lane-${lane}`,
	x: FIRST_NODE_X + column * (NODE_WIDTH + NODE_X_GAP),
	y: lane * LANE_HEIGHT + NODE_Y_OFFSET,
	width: NODE_WIDTH,
	height: NODE_HEIGHT,
	column,
	inCycle: false,
});

const _largeBundle = (n: number): JtbdBundle => {
	const jtbds: JtbdSpec[] = [];
	for (let i = 0; i < n; i++) {
		jtbds.push({
			id: `jtbd_${i}`,
			title: `JTBD ${i}`,
			actor: { role: `lane_${i % 8}` },
			data_capture: [],
			edge_cases: [],
			documents_required: [],
			approvals: [],
			notifications: [],
			sla: { resolution: "PT1H" },
			data_sensitivity: "low",
			compliance: [],
		} as unknown as JtbdSpec);
	}
	return {
		version: "1.0.0",
		domain: "synthetic_load",
		jtbds,
	} as unknown as JtbdBundle;
};

describe("nodesInViewport", () => {
	const nodes = [
		_node("a", 0, 0), // x=200, y=20
		_node("b", 5, 0), // x=200 + 5*(NODE_WIDTH+gap)
		_node("c", 10, 0),
		_node("d", 0, 5),
	];

	it("returns nodes overlapping the viewport rect", () => {
		const viewport: JobMapViewport = { x: 0, y: 0, width: 400, height: 200 };
		const visible = nodesInViewport(nodes, viewport, 0);
		expect(visible.map((n) => n.jtbdId)).toContain("a");
		expect(visible.map((n) => n.jtbdId)).not.toContain("c");
	});

	it("retains cycle-flagged nodes regardless of viewport", () => {
		const cycleNode: NodeLayout = { ..._node("zzz", 99, 99), inCycle: true };
		const visible = nodesInViewport(
			[...nodes, cycleNode],
			{ x: 0, y: 0, width: 50, height: 50 },
			0,
		);
		expect(visible.map((n) => n.jtbdId)).toContain("zzz");
	});

	it("applies overscan margin so the visible set widens with overscan", () => {
		const viewport: JobMapViewport = { x: 0, y: 0, width: 100, height: 100 };
		// A node at column=1, lane=0 is offscreen for a 100×100 viewport
		// with no overscan but inside a viewport extended by NODE_WIDTH +
		// NODE_X_GAP overscan.
		const offNode = _node("just_off", 1, 0);
		const noOverscan = nodesInViewport([offNode], viewport, 0);
		const widerOverscan = nodesInViewport(
			[offNode],
			viewport,
			NODE_WIDTH + NODE_X_GAP + FIRST_NODE_X,
		);
		expect(noOverscan.length).toBe(0);
		expect(widerOverscan.map((n) => n.jtbdId)).toContain("just_off");
	});
});

describe("edgesInViewport", () => {
	it("keeps edges where both endpoints are visible", () => {
		const visibleNodeIds = new Set(["a", "b"]);
		const edges: EdgeLayout[] = [
			{ id: "a->b", source: "a", target: "b", crossLane: false },
			{ id: "a->c", source: "a", target: "c", crossLane: true },
			{ id: "x->y", source: "x", target: "y", crossLane: false },
		];
		const visible = edgesInViewport(edges, visibleNodeIds);
		expect(visible.map((e) => e.id)).toEqual(["a->b"]);
	});
});

describe("VIRTUALISATION_THRESHOLD", () => {
	it("is at least 200 (per audit-fix-plan §4.4 JS-07)", () => {
		expect(VIRTUALISATION_THRESHOLD).toBeGreaterThanOrEqual(200);
	});
});

describe("JobMap virtualisation", () => {
	it("renders all nodes when bundle is below threshold", () => {
		const bundle = _largeBundle(VIRTUALISATION_THRESHOLD - 1);
		const { container } = render(<JobMap bundle={bundle} withReactFlow={false} />);
		const wrapper = container.querySelector('[data-testid="ff-jobmap"]');
		expect(wrapper).toBeTruthy();
		expect(wrapper?.getAttribute("data-virtualised")).toBe("false");
	});

	it("opts into virtualisation at the threshold and renders only the viewport slice", () => {
		const bundle = _largeBundle(VIRTUALISATION_THRESHOLD + 50);
		// Tight viewport: only the first 400×400 px region should render.
		render(
			<JobMap
				bundle={bundle}
				withReactFlow={false}
				viewport={{ x: 0, y: 0, width: 400, height: 400 }}
			/>,
		);
		const wrapper = screen.getByTestId("ff-jobmap");
		expect(wrapper.getAttribute("data-virtualised")).toBe("true");
		const rendered = Number(wrapper.getAttribute("data-rendered-nodes"));
		// Far less than the total — virtualisation actually kicks in.
		expect(rendered).toBeLessThan(VIRTUALISATION_THRESHOLD);
		expect(rendered).toBeGreaterThan(0);
	});

	it("respects virtualise={false} to force-render every node", () => {
		const bundle = _largeBundle(VIRTUALISATION_THRESHOLD + 10);
		render(
			<JobMap
				bundle={bundle}
				withReactFlow={false}
				virtualise={false}
				viewport={{ x: 0, y: 0, width: 400, height: 400 }}
			/>,
		);
		const wrapper = screen.getByTestId("ff-jobmap");
		expect(wrapper.getAttribute("data-virtualised")).toBe("false");
		// All nodes rendered even though a viewport was passed.
		expect(Number(wrapper.getAttribute("data-rendered-nodes"))).toBe(
			VIRTUALISATION_THRESHOLD + 10,
		);
	});

	it("respects a numeric virtualise= override (lower threshold)", () => {
		const bundle = _largeBundle(50);
		render(
			<JobMap
				bundle={bundle}
				withReactFlow={false}
				virtualise={10}
				viewport={{ x: 0, y: 0, width: 400, height: 400 }}
			/>,
		);
		const wrapper = screen.getByTestId("ff-jobmap");
		expect(wrapper.getAttribute("data-virtualised")).toBe("true");
		expect(Number(wrapper.getAttribute("data-rendered-nodes"))).toBeLessThan(50);
	});
});

describe("test_JS_07_virtualized_render", () => {
	it("at 200+ JTBDs the rendered DOM node count is bounded by viewport", () => {
		const bundle = _largeBundle(250);
		const { container } = render(
			<JobMap
				bundle={bundle}
				withReactFlow={false}
				viewport={{ x: 0, y: 0, width: 800, height: 400 }}
			/>,
		);
		const nodeButtons = container.querySelectorAll('[data-testid^="ff-jobmap-node-"]');
		// 250 total bundle. With an 800x400 viewport (+200 overscan in
		// every direction = 1200x800), expect well under half rendered.
		expect(nodeButtons.length).toBeLessThan(250);
		expect(nodeButtons.length).toBeGreaterThan(0);
	});
});
