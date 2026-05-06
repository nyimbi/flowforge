"""ActorConsistencyAnalyzer."""

from __future__ import annotations

from flowforge_jtbd.lint.actors import ActorConsistencyAnalyzer
from flowforge_jtbd.spec import ActorRef, RoleDef

from .conftest import make_bundle, make_full_spec


def test_no_actor_no_findings() -> None:
	spec = make_full_spec("x")
	bundle = make_bundle([spec])
	out = ActorConsistencyAnalyzer().analyze(bundle)
	assert out == {}


def test_role_undeclared_is_warning() -> None:
	spec = make_full_spec(
		"x",
		actor=ActorRef(role="ghost"),
	)
	bundle = make_bundle([spec])
	out = ActorConsistencyAnalyzer().analyze(bundle)
	assert "x" in out
	rules = {i.rule for i in out["x"]}
	assert "actor_role_undeclared" in rules
	assert all(i.severity == "warning" for i in out["x"] if i.rule == "actor_role_undeclared")


def test_authority_insufficient_is_error() -> None:
	spec = make_full_spec(
		"open_account",
		actor=ActorRef(role="banker", tier=3),
	)
	bundle = make_bundle(
		[spec],
		shared_roles={"banker": RoleDef(name="banker", default_tier=1)},
	)
	out = ActorConsistencyAnalyzer().analyze(bundle)
	issues = out["open_account"]
	auth = [i for i in issues if i.rule == "actor_authority_insufficient"]
	assert len(auth) == 1
	assert auth[0].severity == "error"
	assert auth[0].extra["required_tier"] == 3
	assert auth[0].extra["actual_tier"] == 1


def test_tier_at_threshold_is_ok() -> None:
	spec = make_full_spec(
		"x",
		actor=ActorRef(role="banker", tier=2),
	)
	bundle = make_bundle(
		[spec],
		shared_roles={"banker": RoleDef(name="banker", default_tier=2)},
	)
	out = ActorConsistencyAnalyzer().analyze(bundle)
	# No authority issue.
	assert "x" not in out or all(
		i.rule != "actor_authority_insufficient" for i in out["x"]
	)


def test_capacity_conflict_is_warning() -> None:
	# Same role in same context appears as both creator and approver.
	creator = make_full_spec(
		"submit_claim",
		actor=ActorRef(role="clerk", capacity="creator", context="claim"),
	)
	approver = make_full_spec(
		"approve_claim",
		actor=ActorRef(role="clerk", capacity="approver", context="claim"),
	)
	bundle = make_bundle(
		[creator, approver],
		shared_roles={"clerk": RoleDef(name="clerk", default_tier=1)},
	)
	out = ActorConsistencyAnalyzer().analyze(bundle)
	# Both specs receive the warning.
	for jtbd_id in ("submit_claim", "approve_claim"):
		assert any(
			i.rule == "actor_role_conflict" and i.severity == "warning"
			for i in out[jtbd_id]
		)


def test_capacity_conflict_scoped_per_context() -> None:
	# Same role acts as creator+approver but in different contexts.
	# That's allowed.
	a = make_full_spec(
		"a",
		actor=ActorRef(role="clerk", capacity="creator", context="claim"),
	)
	b = make_full_spec(
		"b",
		actor=ActorRef(role="clerk", capacity="approver", context="invoice"),
	)
	bundle = make_bundle(
		[a, b],
		shared_roles={"clerk": RoleDef(name="clerk", default_tier=1)},
	)
	out = ActorConsistencyAnalyzer().analyze(bundle)
	for jtbd_id in ("a", "b"):
		conflicts = [
			i for i in out.get(jtbd_id, [])
			if i.rule == "actor_role_conflict"
		]
		assert conflicts == []


def test_non_conflicting_capacities_are_silent() -> None:
	# Reviewer + reviewer (same capacity twice) is not a conflict.
	a = make_full_spec(
		"a",
		actor=ActorRef(role="clerk", capacity="reviewer", context="claim"),
	)
	b = make_full_spec(
		"b",
		actor=ActorRef(role="clerk", capacity="reviewer", context="claim"),
	)
	bundle = make_bundle(
		[a, b],
		shared_roles={"clerk": RoleDef(name="clerk", default_tier=1)},
	)
	out = ActorConsistencyAnalyzer().analyze(bundle)
	assert out == {}


def test_custom_conflict_pairs() -> None:
	# Host extends conflicting pairs to flag custom combinations.
	a = make_full_spec(
		"a",
		actor=ActorRef(role="clerk", capacity="initiator", context="claim"),
	)
	b = make_full_spec(
		"b",
		actor=ActorRef(role="clerk", capacity="closer", context="claim"),
	)
	bundle = make_bundle(
		[a, b],
		shared_roles={"clerk": RoleDef(name="clerk", default_tier=1)},
	)
	analyzer = ActorConsistencyAnalyzer(
		conflicting_capacity_pairs=frozenset({frozenset({"initiator", "closer"})}),
	)
	out = analyzer.analyze(bundle)
	for jtbd_id in ("a", "b"):
		assert any(i.rule == "actor_role_conflict" for i in out[jtbd_id])
