"""Pluggable rule registry.

Per ``framework/docs/flowforge-evolution.md`` §4.4, two ports drive
extension: ``JtbdRule`` (one rule, returns issues for a spec) and
``JtbdRulePack`` (a named bag of rules, typically one per domain).

E-4 ships the protocols and the registry. E-5 + E-17 layer in concrete
per-domain packs (banking, healthcare, …).
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from ..spec import JtbdBundle, JtbdLintSpec
from .results import Issue


@runtime_checkable
class JtbdRule(Protocol):
	"""A single lint rule.

	Implementations expose a stable ``rule_id`` and a ``check`` callable
	that returns the issues found for the given spec. Rules that
	produce bundle-level findings (i.e., not bound to a specific spec)
	may receive ``spec=None``.
	"""

	rule_id: str

	def check(
		self,
		bundle: JtbdBundle,
		spec: JtbdLintSpec | None,
	) -> list[Issue]:
		...


@runtime_checkable
class JtbdRulePack(Protocol):
	"""A named collection of rules, usually scoped to one domain."""

	pack_id: str

	def rules(self) -> list[JtbdRule]:
		...


class StaticRulePack:
	"""Trivial :class:`JtbdRulePack` backed by a fixed list.

	Useful for tests and for small inline packs that do not warrant a
	dedicated module.
	"""

	def __init__(self, pack_id: str, rules: Iterable[JtbdRule]) -> None:
		assert pack_id, "pack_id must be non-empty"
		self.pack_id = pack_id
		self._rules: list[JtbdRule] = list(rules)

	def rules(self) -> list[JtbdRule]:
		return list(self._rules)


class RuleRegistry:
	"""Collects rule packs and exposes a flat list of rules."""

	def __init__(self, packs: Iterable[JtbdRulePack] | None = None) -> None:
		self._packs: dict[str, JtbdRulePack] = {}
		if packs is not None:
			for pack in packs:
				self.register(pack)

	def register(self, pack: JtbdRulePack) -> None:
		assert pack.pack_id, "pack_id must be non-empty"
		assert pack.pack_id not in self._packs, (
			f"duplicate rule pack id: {pack.pack_id!r}"
		)
		self._packs[pack.pack_id] = pack

	def unregister(self, pack_id: str) -> None:
		self._packs.pop(pack_id, None)

	def packs(self) -> list[JtbdRulePack]:
		return list(self._packs.values())

	def all_rules(self) -> list[JtbdRule]:
		out: list[JtbdRule] = []
		seen: set[str] = set()
		for pack in self._packs.values():
			for rule in pack.rules():
				if rule.rule_id in seen:
					# Last-registered pack wins for duplicate ids; this
					# keeps host overrides predictable.
					continue
				seen.add(rule.rule_id)
				out.append(rule)
		return out


__all__ = ["JtbdRule", "JtbdRulePack", "RuleRegistry", "StaticRulePack"]
