/**
 * Pure trace builder — turns a `JtbdBundle` (or a custom event list)
 * into the firing order the animation walks through.
 *
 * Two strategies live here:
 *
 *   * `buildDefaultTrace(bundle)` — deterministic topological order
 *     across `requires` edges. Same algorithm as
 *     :mod:`flowforge_jtbd.lint.dependencies` (Kahn's algorithm) so
 *     the editor's preview matches what the linter accepts. Cycle
 *     members are appended at the end in insertion order so the
 *     animation never deadlocks.
 *
 *   * `buildTraceFromEvents(bundle, events)` — bind explicit
 *     `<jtbd_id>` markers from a sample-input run. Unknown ids are
 *     dropped (the linter is the layer that flags them as errors).
 *
 * The shape we emit is a flat array of `TraceStep` objects rather
 * than just ids so the future debugger ports (E-12 fault injection,
 * E-13 regression diff) can decorate each step without rewriting the
 * animation's data path.
 */

import type { JtbdBundle, JtbdSpec } from "./types.js";

export interface TraceStep {
	jtbdId: string;
	/** Zero-based step index. */
	index: number;
	/** Optional human-readable note shown in the tooltip / log. */
	note?: string;
}

export interface Trace {
	steps: TraceStep[];
}

/**
 * Topological order via Kahn's algorithm. Nodes that participate in a
 * cycle land at the end of the trace in insertion order — the linter
 * surfaces the cycle elsewhere; the animation just keeps walking so
 * the author can still preview the rest of the bundle.
 */
export function buildDefaultTrace(bundle: JtbdBundle): Trace {
	const specs = bundle.jtbds;
	const ids = specs.map((s) => s.id);
	const idSet = new Set(ids);
	const inDegree = new Map<string, number>();
	const adj = new Map<string, string[]>();
	for (const spec of specs) {
		inDegree.set(spec.id, 0);
		adj.set(spec.id, []);
	}
	for (const spec of specs) {
		for (const req of spec.requires ?? []) {
			if (!idSet.has(req)) {
				continue;
			}
			adj.get(req)?.push(spec.id);
			inDegree.set(spec.id, (inDegree.get(spec.id) ?? 0) + 1);
		}
	}
	// Stable: walk specs in declared order so equal-depth nodes stay
	// in the order the author wrote them.
	const queue: string[] = [];
	for (const spec of specs) {
		if ((inDegree.get(spec.id) ?? 0) === 0) {
			queue.push(spec.id);
		}
	}
	const ordered: string[] = [];
	const seen = new Set<string>();
	while (queue.length > 0) {
		const id = queue.shift();
		if (id === undefined || seen.has(id)) {
			continue;
		}
		ordered.push(id);
		seen.add(id);
		for (const next of adj.get(id) ?? []) {
			const remaining = (inDegree.get(next) ?? 0) - 1;
			inDegree.set(next, remaining);
			if (remaining === 0) {
				queue.push(next);
			}
		}
	}
	// Append any remaining ids (cycle members) in declared order.
	for (const spec of specs) {
		if (!seen.has(spec.id)) {
			ordered.push(spec.id);
			seen.add(spec.id);
		}
	}
	return {
		steps: ordered.map((id, idx) => ({ jtbdId: id, index: idx })),
	};
}

/**
 * Build a trace from an ordered list of `<jtbd_id>` event names. Unknown
 * ids are dropped. The same JTBD may appear multiple times (a real
 * workflow can re-fire `claim_triage` after rework).
 */
export function buildTraceFromEvents(
	bundle: JtbdBundle,
	events: string[],
): Trace {
	const known = new Map<string, JtbdSpec>();
	for (const spec of bundle.jtbds) {
		known.set(spec.id, spec);
	}
	const steps: TraceStep[] = [];
	let idx = 0;
	for (const event of events) {
		if (!known.has(event)) {
			continue;
		}
		steps.push({ jtbdId: event, index: idx });
		idx += 1;
	}
	return { steps };
}
