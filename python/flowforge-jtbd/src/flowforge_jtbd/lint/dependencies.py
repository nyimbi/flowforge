"""Dependency-graph analyzer.

Per ``framework/docs/jtbd-editor-arch.md`` §2.3, each JTBD declares
``requires: [<other_jtbd_id>]``. The linter:

- Builds a directed graph from those edges.
- Detects cycles (Tarjan's strongly-connected-components — every SCC
  with more than one node, or a single-node SCC with a self-loop, is
  a cycle).
- Reports unknown / dangling ``requires`` ids.
- Emits a topological order for the editor sidebar (Kahn's algorithm).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..spec import JtbdBundle
from .results import Issue


_DOC_URL = "/docs/jtbd-editor#dependencies"


@dataclass(frozen=True)
class DependencyCycle:
	"""A detected cycle in the dependency graph.

	``nodes`` is the SCC's member list in deterministic order; ``path``
	is one concrete edge cycle that traverses every node and returns
	to the start (helpful for human-readable error messages).
	"""

	nodes: tuple[str, ...]
	path: tuple[str, ...]


@dataclass
class DependencyGraph:
	"""Dependency-graph analysis result for a bundle.

	Build via :meth:`build`; consumers read :attr:`issues` for lint
	output and :attr:`topological_order` for sidebar / build ordering.
	"""

	edges: dict[str, list[str]] = field(default_factory=dict)
	cycles: list[DependencyCycle] = field(default_factory=list)
	issues: list[Issue] = field(default_factory=list)
	topological_order: list[str] | None = None

	@classmethod
	def build(cls, bundle: JtbdBundle) -> "DependencyGraph":
		graph = cls()
		graph._populate(bundle)
		graph._detect_unknown_edges(bundle)
		graph._detect_cycles()
		graph._compute_topological_order()
		return graph

	def _populate(self, bundle: JtbdBundle) -> None:
		known = {spec.jtbd_id for spec in bundle.jtbds}
		assert len(known) == len(bundle.jtbds), (
			"duplicate jtbd_id in bundle — caller should dedupe before"
			" lint"
		)
		for spec in bundle.jtbds:
			# Preserve declared order so cycle paths are deterministic.
			self.edges[spec.jtbd_id] = list(spec.requires)

	def _detect_unknown_edges(self, bundle: JtbdBundle) -> None:
		known = {spec.jtbd_id for spec in bundle.jtbds}
		for source, targets in self.edges.items():
			seen: set[str] = set()
			for target in targets:
				if target in seen:
					self.issues.append(Issue(
						severity="warning",
						rule="duplicate_requires",
						message=(
							f"{source!r} declares requires={target!r} "
							f"more than once"
						),
						fixhint="Remove duplicates from 'requires'.",
						related_jtbds=[target],
						doc_url=_DOC_URL,
					))
					continue
				seen.add(target)
				if target not in known:
					self.issues.append(Issue(
						severity="error",
						rule="requires_unknown_jtbd",
						message=(
							f"{source!r} requires {target!r}, which is "
							f"not in the bundle"
						),
						fixhint=(
							"Add the dependency to the bundle or remove "
							"the requires entry."
						),
						related_jtbds=[target],
						doc_url=_DOC_URL,
					))
				if target == source:
					self.issues.append(Issue(
						severity="error",
						rule="requires_self",
						message=f"{source!r} requires itself",
						fixhint="Remove the self-edge.",
						related_jtbds=[source],
						doc_url=_DOC_URL,
					))

	# ------------------------------------------------------------------
	# Tarjan's SCC. Iterative implementation so deep dependency graphs
	# do not blow the recursion limit. Yields SCCs in reverse-topological
	# order, which we re-sort for stable output.
	# ------------------------------------------------------------------
	def _detect_cycles(self) -> None:
		index_of: dict[str, int] = {}
		lowlink: dict[str, int] = {}
		on_stack: set[str] = set()
		stack: list[str] = []
		index_counter = 0
		sccs: list[list[str]] = []

		nodes_in_order = list(self.edges.keys())

		# Iterative Tarjan via explicit work list. Each frame is
		# ``(node, neighbours_iter)``. When neighbours are exhausted
		# we pop and finalise lowlink + maybe emit an SCC.
		for start in nodes_in_order:
			if start in index_of:
				continue
			work: list[tuple[str, list[str], int]] = []

			def push(node: str) -> None:
				nonlocal index_counter
				index_of[node] = index_counter
				lowlink[node] = index_counter
				index_counter += 1
				stack.append(node)
				on_stack.add(node)
				neighbours = [
					n for n in self.edges.get(node, [])
					if n in self.edges  # ignore unknown targets
				]
				work.append((node, neighbours, 0))

			push(start)

			while work:
				node, neighbours, cursor = work[-1]
				if cursor < len(neighbours):
					next_node = neighbours[cursor]
					work[-1] = (node, neighbours, cursor + 1)
					if next_node not in index_of:
						push(next_node)
					elif next_node in on_stack:
						lowlink[node] = min(
							lowlink[node], index_of[next_node],
						)
					continue
				# Finalise: all neighbours processed.
				work.pop()
				if work:
					parent = work[-1][0]
					lowlink[parent] = min(lowlink[parent], lowlink[node])
				if lowlink[node] == index_of[node]:
					component: list[str] = []
					while True:
						top = stack.pop()
						on_stack.discard(top)
						component.append(top)
						if top == node:
							break
					sccs.append(component)

		for component in sccs:
			if len(component) > 1:
				cycle = self._materialise_cycle(component)
				self.cycles.append(cycle)
				self._report_cycle(cycle)
				continue
			# Single-node SCC: only a cycle if the node has a self-edge.
			only = component[0]
			if only in self.edges.get(only, []):
				cycle = DependencyCycle(
					nodes=(only,),
					path=(only, only),
				)
				self.cycles.append(cycle)
				self._report_cycle(cycle)

	def _materialise_cycle(self, component: list[str]) -> DependencyCycle:
		"""Return a deterministic cycle path through ``component``."""
		members = sorted(component)
		# Walk a concrete cycle starting from the lexicographically
		# smallest member, choosing the smallest in-component neighbour
		# at each step. This is bounded by len(component) since every
		# node sits on at least one cycle within the SCC.
		member_set = set(component)
		start = members[0]
		path = [start]
		current = start
		while True:
			candidates = sorted(
				n for n in self.edges.get(current, [])
				if n in member_set
			)
			assert candidates, (
				"every SCC node has at least one edge into the SCC"
			)
			# Prefer to close the cycle if we can.
			next_node = start if start in candidates else candidates[0]
			path.append(next_node)
			if next_node == start:
				break
			# Defensive bound — should never trigger because Tarjan's
			# guarantee gives us a cycle within ``component`` of length
			# at most len(component) + 1.
			if len(path) > len(component) + 1:
				break
			current = next_node
		return DependencyCycle(
			nodes=tuple(members),
			path=tuple(path),
		)

	def _report_cycle(self, cycle: DependencyCycle) -> None:
		path = " → ".join(cycle.path)
		self.issues.append(Issue(
			severity="error",
			rule="cycle_detected",
			message=f"dependency cycle: {path}",
			fixhint=(
				"Break the cycle by inverting one edge or extracting a "
				"shared prerequisite into a third JTBD."
			),
			cycle=list(cycle.path),
			related_jtbds=list(cycle.nodes),
			doc_url=_DOC_URL,
		))

	def _compute_topological_order(self) -> None:
		# Skip topo sort if any cycle exists; the order would be
		# undefined.
		if self.cycles:
			self.topological_order = None
			return

		# E-59 / J-11: Kahn's algorithm, tie-broken alphabetically for
		# determinism. The graph edge ``a requires b`` means b must run
		# BEFORE a, so we sort by out-degree (number of unsatisfied
		# requires) and consume nodes whose requires are all satisfied.
		# A "prerequisite" — out_degree == 0 — has no remaining requires.
		ordered: list[str] = []
		# Build reverse adjacency: for node b, who requires b?
		reverse: dict[str, list[str]] = {node: [] for node in self.edges}
		for source, targets in self.edges.items():
			for target in targets:
				if target in reverse:
					reverse[target].append(source)
		out_degree = {
			node: len(set(self.edges.get(node, [])))
			for node in self.edges
		}
		ready = sorted(
			node for node, degree in out_degree.items() if degree == 0
		)
		consumed: set[str] = set()
		while ready:
			node = ready.pop(0)
			ordered.append(node)
			consumed.add(node)
			# Anyone that requires ``node`` may now be ready.
			for dependent in reverse.get(node, []):
				remaining = {
					target for target in self.edges.get(dependent, [])
					if target not in consumed
				}
				if not remaining and dependent not in consumed:
					if dependent not in ready:
						# Insert keeping ready alphabetical.
						ready.append(dependent)
						ready.sort()
		if len(ordered) != len(self.edges):
			# Hit only if a cycle slipped past _detect_cycles, which
			# means the graph state is inconsistent — surface it.
			self.topological_order = None
			return
		self.topological_order = ordered


__all__ = ["DependencyCycle", "DependencyGraph"]
