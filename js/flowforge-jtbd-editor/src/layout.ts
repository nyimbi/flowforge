/**
 * Pure swimlane layout for the JTBD job map.
 *
 * Given a `JtbdBundle`, group JTBDs by actor role (one swimlane per
 * role), compute a topological order across `requires` edges, and
 * assign each JTBD an `(x, y)` position so dependencies always flow
 * left-to-right within their lane (or jump lanes when an upstream
 * JTBD lives elsewhere).
 *
 * The layout is deterministic — same bundle in, same positions out —
 * which is what the unit tests rely on. Cycles in the `requires`
 * graph fall back to insertion order; the linter (E-4) is the layer
 * that flags them. We never throw on cycle here because the editor
 * needs to render an in-progress bundle even when it's invalid.
 *
 * The `JobMap` component consumes the structured output below; lane
 * height + node size are encoded as constants here so tests can pin
 * exact pixel positions when asserting layout.
 */

import type { JtbdBundle, JtbdSpec } from "./types.js";

export const LANE_HEIGHT = 140;
export const LANE_HEADER_WIDTH = 160;
export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 80;
export const NODE_X_GAP = 40;
export const NODE_Y_OFFSET = 30;
export const FIRST_NODE_X = LANE_HEADER_WIDTH + 40;

export interface LaneLayout {
	/** Actor role for this lane. */
	role: string;
	/** Zero-based vertical index. */
	index: number;
	/** Top-left y of the lane. */
	y: number;
	/** Lane height (constant per release). */
	height: number;
}

export interface NodeLayout {
	jtbdId: string;
	role: string;
	title: string;
	column: number;
	x: number;
	y: number;
	width: number;
	height: number;
	/** True for nodes that participate in a cycle the linter would
	 * later flag. The component renders them with a warning ring. */
	inCycle: boolean;
}

export interface EdgeLayout {
	id: string;
	source: string;
	target: string;
	/** True if the edge crosses two different actor lanes. The
	 * component renders cross-lane edges in a different colour so the
	 * eye picks them up. */
	crossLane: boolean;
}

export interface JobMapLayout {
	lanes: LaneLayout[];
	nodes: NodeLayout[];
	edges: EdgeLayout[];
	/** Total canvas width — derived from the rightmost column. */
	width: number;
	/** Total canvas height — `lanes.length * LANE_HEIGHT`. */
	height: number;
}

/**
 * Compute lane assignments + topological column for every JTBD.
 *
 * Lanes are sorted by first appearance of an actor role in
 * `bundle.jtbds`, which gives stable ordering as the author edits.
 * Nodes within a lane are sorted by topological depth (longest path
 * from a root). Cycles, if any, are reported via `inCycle: true` on
 * every node in the SCC; their column falls back to insertion order.
 */
export function layoutJobMap(bundle: JtbdBundle): JobMapLayout {
	const specs = bundle.jtbds;
	const byId = new Map<string, JtbdSpec>();
	for (const s of specs) {
		byId.set(s.id, s);
	}

	// Lane order = order in which a new actor role first appears.
	const laneIndex = new Map<string, number>();
	for (const s of specs) {
		const role = s.actor.role;
		if (!laneIndex.has(role)) {
			laneIndex.set(role, laneIndex.size);
		}
	}
	const lanes: LaneLayout[] = Array.from(laneIndex.entries()).map(
		([role, index]) => ({
			role,
			index,
			y: index * LANE_HEIGHT,
			height: LANE_HEIGHT,
		}),
	);

	const { columns, cyclic } = topologicalColumns(specs, byId);

	const nodes: NodeLayout[] = specs.map((spec) => {
		const role = spec.actor.role;
		const lane = laneIndex.get(role) ?? 0;
		const col = columns.get(spec.id) ?? 0;
		return {
			jtbdId: spec.id,
			role,
			title: spec.title || spec.id,
			column: col,
			x: FIRST_NODE_X + col * (NODE_WIDTH + NODE_X_GAP),
			y: lane * LANE_HEIGHT + NODE_Y_OFFSET,
			width: NODE_WIDTH,
			height: NODE_HEIGHT,
			inCycle: cyclic.has(spec.id),
		};
	});

	const edges: EdgeLayout[] = [];
	for (const spec of specs) {
		const sourceRole = spec.actor.role;
		for (const upstreamId of spec.requires ?? []) {
			const upstream = byId.get(upstreamId);
			if (!upstream) {
				// Linter (E-4) flags missing dependencies; we just skip
				// them in the layout so the canvas does not point an
				// arrow at a ghost.
				continue;
			}
			edges.push({
				id: `${upstreamId}->${spec.id}`,
				source: upstreamId,
				target: spec.id,
				crossLane: upstream.actor.role !== sourceRole,
			});
		}
	}

	const maxColumn = nodes.reduce((m, n) => Math.max(m, n.column), 0);
	const width = FIRST_NODE_X + (maxColumn + 1) * (NODE_WIDTH + NODE_X_GAP);
	const height = Math.max(LANE_HEIGHT, lanes.length * LANE_HEIGHT);

	return { lanes, nodes, edges, width, height };
}

/**
 * Compute the topological column index for each JTBD plus the set of
 * jtbd_ids that participate in any cycle.
 *
 * The algorithm runs a depth-first search; back-edges mark cycle
 * members. Tree-edges define depth (column). Forward / cross edges
 * relax depth via `max(depth)`. This is a small graph (<200 nodes
 * per the perf budget) so the simple recursive DFS is fine.
 */
function topologicalColumns(
	specs: JtbdSpec[],
	byId: Map<string, JtbdSpec>,
): { columns: Map<string, number>; cyclic: Set<string> } {
	const columns = new Map<string, number>();
	const cyclic = new Set<string>();
	const inStack = new Set<string>();

	const visit = (id: string, stack: string[]): number => {
		if (columns.has(id)) {
			return columns.get(id) ?? 0;
		}
		if (inStack.has(id)) {
			// Mark every node on the current stack from `id` onward
			// as part of the cycle.
			const fromIdx = stack.indexOf(id);
			if (fromIdx >= 0) {
				for (let i = fromIdx; i < stack.length; i++) {
					const sid = stack[i];
					if (sid !== undefined) {
						cyclic.add(sid);
					}
				}
			}
			cyclic.add(id);
			return 0;
		}
		const spec = byId.get(id);
		if (!spec) {
			return 0;
		}
		inStack.add(id);
		stack.push(id);
		let depth = 0;
		for (const req of spec.requires ?? []) {
			if (!byId.has(req)) {
				// Missing dependency — treat as depth 0 so the node
				// floats left.
				continue;
			}
			depth = Math.max(depth, visit(req, stack) + 1);
		}
		stack.pop();
		inStack.delete(id);
		columns.set(id, depth);
		return depth;
	};

	for (const s of specs) {
		visit(s.id, []);
	}
	return { columns, cyclic };
}
