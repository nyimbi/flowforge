"""RuleRegistry + JtbdRule / JtbdRulePack protocols."""

from __future__ import annotations

import pytest

from flowforge_jtbd.lint.registry import (
	JtbdRule,
	JtbdRulePack,
	RuleRegistry,
	StaticRulePack,
)
from flowforge_jtbd.lint.results import Issue
from flowforge_jtbd.spec import JtbdBundle, JtbdLintSpec


class _AlwaysFlag:
	rule_id = "always-flag"

	def check(
		self,
		bundle: JtbdBundle,
		spec: JtbdLintSpec | None,
	) -> list[Issue]:
		if spec is None:
			return []
		return [Issue(
			severity="info",
			rule=self.rule_id,
			message=f"flagged {spec.jtbd_id}",
		)]


class _OtherRule:
	rule_id = "other"

	def check(
		self,
		bundle: JtbdBundle,
		spec: JtbdLintSpec | None,
	) -> list[Issue]:
		return []


def test_protocols_are_runtime_checkable() -> None:
	rule = _AlwaysFlag()
	assert isinstance(rule, JtbdRule)

	pack = StaticRulePack("p", [rule])
	assert isinstance(pack, JtbdRulePack)


def test_registry_roundtrip() -> None:
	reg = RuleRegistry()
	pack = StaticRulePack("test", [_AlwaysFlag(), _OtherRule()])
	reg.register(pack)
	rules = reg.all_rules()
	assert {r.rule_id for r in rules} == {"always-flag", "other"}


def test_registry_constructor_accepts_packs() -> None:
	pack = StaticRulePack("p", [_AlwaysFlag()])
	reg = RuleRegistry(packs=[pack])
	assert [p.pack_id for p in reg.packs()] == ["p"]


def test_duplicate_pack_id_rejected() -> None:
	pack_a = StaticRulePack("dup", [_AlwaysFlag()])
	pack_b = StaticRulePack("dup", [_OtherRule()])
	reg = RuleRegistry()
	reg.register(pack_a)
	with pytest.raises(AssertionError):
		reg.register(pack_b)


def test_unregister() -> None:
	reg = RuleRegistry()
	pack = StaticRulePack("p", [_AlwaysFlag()])
	reg.register(pack)
	reg.unregister("p")
	assert reg.packs() == []
	# Unregistering an absent pack is a no-op.
	reg.unregister("missing")


def test_duplicate_rule_id_first_wins() -> None:
	# Two packs both expose a rule with id "always-flag". The first
	# wins; the second's instance is dropped.
	first = _AlwaysFlag()
	second = _AlwaysFlag()
	pack1 = StaticRulePack("p1", [first])
	pack2 = StaticRulePack("p2", [second])
	reg = RuleRegistry(packs=[pack1, pack2])
	rules = reg.all_rules()
	assert len(rules) == 1
	assert rules[0] is first
