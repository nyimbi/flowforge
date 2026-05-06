"""Top-level linter orchestrator.

Wires the lifecycle, dependency, and actor analyzers together with the
pluggable rule registry and emits a :class:`LintReport` per
``framework/docs/jtbd-editor-arch.md`` §2.5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..spec import JtbdBundle, coerce_bundle
from .actors import ActorConsistencyAnalyzer
from .dependencies import DependencyGraph
from .lifecycle import LifecycleAnalyzer
from .registry import RuleRegistry
from .results import Issue, JtbdResult, LintReport


@dataclass
class Linter:
	"""Run every analyzer + registered rule and aggregate results.

	The defaults match the canonical lint behaviour described in the
	architecture doc. Callers may swap out any analyzer with a
	pre-configured instance (e.g., a ``LifecycleAnalyzer`` with custom
	required stages for a niche domain).
	"""

	lifecycle: LifecycleAnalyzer = field(default_factory=LifecycleAnalyzer)
	actors: ActorConsistencyAnalyzer = field(
		default_factory=ActorConsistencyAnalyzer,
	)
	registry: RuleRegistry = field(default_factory=RuleRegistry)

	def lint(self, bundle: JtbdBundle | dict[str, Any]) -> LintReport:
		bundle_obj = coerce_bundle(bundle)
		assert bundle_obj.bundle_id, "bundle_id must be non-empty"

		issues_by_spec: dict[str, list[Issue]] = {
			spec.jtbd_id: [] for spec in bundle_obj.jtbds
		}
		bundle_issues: list[Issue] = []

		# Dependency analysis is bundle-level. We attach
		# requires_unknown_jtbd / cycle issues to bundle_issues since
		# they can span multiple specs.
		dep = DependencyGraph.build(bundle_obj)
		bundle_issues.extend(dep.issues)
		topo = dep.topological_order

		# Lifecycle is per-spec.
		for spec in bundle_obj.jtbds:
			issues_by_spec[spec.jtbd_id].extend(
				self.lifecycle.analyze(bundle_obj, spec),
			)

		# Actor consistency is bundle-level but emits per-spec issues.
		actor_issues = self.actors.analyze(bundle_obj)
		for jtbd_id, issues in actor_issues.items():
			# Defensive: an analyzer may legitimately raise an issue
			# against a spec that isn't in the bundle (e.g., delegated
			# audits). Bucket those into bundle_issues.
			if jtbd_id in issues_by_spec:
				issues_by_spec[jtbd_id].extend(issues)
			else:
				bundle_issues.extend(issues)

		# Pluggable rules. Spec=None means "bundle-level" rule.
		for rule in self.registry.all_rules():
			# Bundle-level invocation
			bundle_issues.extend(rule.check(bundle_obj, None))
			# Per-spec invocation
			for spec in bundle_obj.jtbds:
				issues_by_spec[spec.jtbd_id].extend(
					rule.check(bundle_obj, spec),
				)

		results = [
			JtbdResult(
				jtbd_id=spec.jtbd_id,
				version=spec.version,
				issues=issues_by_spec[spec.jtbd_id],
			)
			for spec in bundle_obj.jtbds
		]
		ok = (
			not any(
				issue.severity == "error" for issue in bundle_issues
			)
			and not any(
				issue.severity == "error"
				for result in results
				for issue in result.issues
			)
		)
		return LintReport(
			ok=ok,
			results=results,
			bundle_issues=bundle_issues,
			topological_order=topo,
		)


__all__ = ["Linter"]
