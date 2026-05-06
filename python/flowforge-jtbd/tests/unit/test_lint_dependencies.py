"""DependencyGraph cycle detection + topological order."""

from __future__ import annotations

from flowforge_jtbd.lint.dependencies import DependencyGraph

from .conftest import make_bundle, make_full_spec


def test_acyclic_topological_order() -> None:
	a = make_full_spec("a", requires=["b"])
	b = make_full_spec("b", requires=["c"])
	c = make_full_spec("c")
	bundle = make_bundle([a, b, c])
	dep = DependencyGraph.build(bundle)
	assert dep.cycles == []
	# Prerequisites come before dependents.
	order = dep.topological_order
	assert order is not None
	assert order.index("c") < order.index("b") < order.index("a")


def test_self_loop_is_cycle() -> None:
	a = make_full_spec("a", requires=["a"])
	bundle = make_bundle([a])
	dep = DependencyGraph.build(bundle)
	# Self-loop both flags as requires_self AND as a cycle.
	rules = {i.rule for i in dep.issues}
	assert "requires_self" in rules
	assert "cycle_detected" in rules
	assert dep.topological_order is None


def test_two_node_cycle() -> None:
	a = make_full_spec("a", requires=["b"])
	b = make_full_spec("b", requires=["a"])
	bundle = make_bundle([a, b])
	dep = DependencyGraph.build(bundle)
	cycle_issues = [i for i in dep.issues if i.rule == "cycle_detected"]
	assert len(cycle_issues) == 1
	cycle = cycle_issues[0].cycle
	assert cycle is not None
	# Path closes on the start node.
	assert cycle[0] == cycle[-1]
	assert set(cycle) == {"a", "b"}


def test_three_node_cycle() -> None:
	a = make_full_spec("a", requires=["b"])
	b = make_full_spec("b", requires=["c"])
	c = make_full_spec("c", requires=["a"])
	bundle = make_bundle([a, b, c])
	dep = DependencyGraph.build(bundle)
	cycles = [i for i in dep.issues if i.rule == "cycle_detected"]
	assert len(cycles) == 1
	# Topological order is undefined when a cycle exists.
	assert dep.topological_order is None


def test_unknown_dependency_target_is_error() -> None:
	a = make_full_spec("a", requires=["ghost"])
	bundle = make_bundle([a])
	dep = DependencyGraph.build(bundle)
	rules = {i.rule for i in dep.issues}
	assert "requires_unknown_jtbd" in rules


def test_duplicate_requires_is_warning() -> None:
	a = make_full_spec("a", requires=["b", "b"])
	b = make_full_spec("b")
	bundle = make_bundle([a, b])
	dep = DependencyGraph.build(bundle)
	rules = {i.rule for i in dep.issues}
	assert "duplicate_requires" in rules
	# Topological order still computed (duplicate is just a warning).
	assert dep.topological_order is not None


def test_diamond_dependency_topo_order() -> None:
	# d depends on b and c, both of which depend on a.
	a = make_full_spec("a")
	b = make_full_spec("b", requires=["a"])
	c = make_full_spec("c", requires=["a"])
	d = make_full_spec("d", requires=["b", "c"])
	bundle = make_bundle([a, b, c, d])
	dep = DependencyGraph.build(bundle)
	order = dep.topological_order
	assert order is not None
	assert order.index("a") < order.index("b") < order.index("d")
	assert order.index("a") < order.index("c") < order.index("d")
	assert dep.cycles == []


def test_disconnected_components() -> None:
	# Two independent islands. Topo order must include both.
	a = make_full_spec("a", requires=["b"])
	b = make_full_spec("b")
	x = make_full_spec("x", requires=["y"])
	y = make_full_spec("y")
	bundle = make_bundle([a, b, x, y])
	dep = DependencyGraph.build(bundle)
	order = dep.topological_order
	assert order is not None
	assert set(order) == {"a", "b", "x", "y"}
	assert order.index("b") < order.index("a")
	assert order.index("y") < order.index("x")


def test_large_chain_does_not_recurse() -> None:
	# Iterative Tarjan must handle long chains beyond Python's default
	# recursion limit. 5_000 nodes is comfortably above the default.
	specs = []
	for i in range(5000):
		requires = [f"n{i - 1}"] if i > 0 else []
		specs.append(make_full_spec(f"n{i}", requires=requires))
	bundle = make_bundle(specs)
	dep = DependencyGraph.build(bundle)
	assert dep.cycles == []
	order = dep.topological_order
	assert order is not None
	assert len(order) == 5000
	assert order[0] == "n0"
	assert order[-1] == "n4999"
