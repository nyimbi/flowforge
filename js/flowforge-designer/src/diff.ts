import type { DiffEntry, WorkflowDef } from "./types.js";

const indexById = <T extends { id: string }>(items: T[]): Map<string, T> => {
	const out = new Map<string, T>();
	for (const item of items) out.set(item.id, item);
	return out;
};

const shallowEqual = (a: unknown, b: unknown): boolean => {
	if (a === b) return true;
	if (a === null || b === null) return false;
	if (typeof a !== "object" || typeof b !== "object") return false;
	const ao = a as Record<string, unknown>;
	const bo = b as Record<string, unknown>;
	const ak = Object.keys(ao);
	const bk = Object.keys(bo);
	if (ak.length !== bk.length) return false;
	for (const k of ak) {
		const av = ao[k];
		const bv = bo[k];
		if (typeof av === "object" && av !== null && typeof bv === "object" && bv !== null) {
			if (JSON.stringify(av) !== JSON.stringify(bv)) return false;
		} else if (av !== bv) {
			return false;
		}
	}
	return true;
};

/**
 * Compute a structural diff between two workflow versions.
 *
 * Output is a flat list of `added | removed | modified` entries, each
 * pointing to a JSON-pointer-ish path. The DiffViewer turns these into a
 * grouped UI; downstream tools (release notes, audit) can consume the same
 * shape directly.
 */
export const diffWorkflows = (
	before: WorkflowDef,
	after: WorkflowDef,
): DiffEntry[] => {
	const entries: DiffEntry[] = [];

	if (before.name !== after.name) {
		entries.push({ kind: "modified", path: "name", before: before.name, after: after.name });
	}
	if (before.version !== after.version) {
		entries.push({
			kind: "modified",
			path: "version",
			before: before.version,
			after: after.version,
		});
	}
	if (before.initial_state !== after.initial_state) {
		entries.push({
			kind: "modified",
			path: "initial_state",
			before: before.initial_state,
			after: after.initial_state,
		});
	}

	const beforeStates = indexById(before.states);
	const afterStates = indexById(after.states);
	for (const [id, s] of afterStates) {
		const prev = beforeStates.get(id);
		if (!prev) {
			entries.push({ kind: "added", path: `states/${id}`, after: s });
		} else if (!shallowEqual(prev, s)) {
			entries.push({ kind: "modified", path: `states/${id}`, before: prev, after: s });
		}
	}
	for (const [id, s] of beforeStates) {
		if (!afterStates.has(id)) {
			entries.push({ kind: "removed", path: `states/${id}`, before: s });
		}
	}

	const beforeTrans = indexById(before.transitions);
	const afterTrans = indexById(after.transitions);
	for (const [id, t] of afterTrans) {
		const prev = beforeTrans.get(id);
		if (!prev) {
			entries.push({ kind: "added", path: `transitions/${id}`, after: t });
		} else if (!shallowEqual(prev, t)) {
			entries.push({ kind: "modified", path: `transitions/${id}`, before: prev, after: t });
		}
	}
	for (const [id, t] of beforeTrans) {
		if (!afterTrans.has(id)) {
			entries.push({ kind: "removed", path: `transitions/${id}`, before: t });
		}
	}

	return entries;
};
