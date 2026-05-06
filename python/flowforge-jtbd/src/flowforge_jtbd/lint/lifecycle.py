"""Lifecycle completeness analyzer.

Per ``framework/docs/jtbd-editor-arch.md`` §2.1, a JTBD bundle covers
five required stages by default: ``discover``, ``execute``,
``error_handle``, ``report``, ``audit``. ``undo`` is optional but
recommended.

Per-domain rule packs (E-5 / E-17) layer additional gating on top —
e.g., ``flowforge-jtbd-banking`` requires ``audit`` AND ``undo`` for
specs declaring ``compliance: [SOX]``.

The analyzer also resolves stage delegation via ``handled_by``: if
``account_open`` declares ``stages: [{name: audit, handled_by:
account_audit_log}]`` and ``account_audit_log`` is in the same bundle
and itself declares ``audit``, completeness is satisfied. A delegation
to a missing JTBD is reported as ``stage_delegation_unresolved``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..spec import (
	DEFAULT_OPTIONAL_STAGES,
	DEFAULT_REQUIRED_STAGES,
	JtbdBundle,
	JtbdLintSpec,
)
from .results import Issue


_DOC_URL = "/docs/jtbd-editor#completeness"


@dataclass(frozen=True)
class LifecycleAnalyzer:
	"""Per-JTBD lifecycle completeness check."""

	required_stages: tuple[str, ...] = DEFAULT_REQUIRED_STAGES
	optional_stages: tuple[str, ...] = DEFAULT_OPTIONAL_STAGES
	# When True, an optional stage that is not declared and not
	# delegated emits an ``info`` issue. Callers that want a quieter
	# linter can set this to False.
	hint_optional: bool = True

	def analyze(self, bundle: JtbdBundle, spec: JtbdLintSpec) -> list[Issue]:
		assert spec.jtbd_id, "spec.jtbd_id must be non-empty"
		issues: list[Issue] = []
		direct = spec.stage_names()
		delegations = spec.stage_delegations()
		bundle_index = bundle.by_id()

		# Duplicate stage declarations within a single spec are a hint
		# that two adjacent edits both added the stage.
		seen: dict[str, int] = {}
		for stage in spec.stages:
			seen[stage.name] = seen.get(stage.name, 0) + 1
		for stage_name, count in seen.items():
			if count > 1:
				issues.append(Issue(
					severity="warning",
					rule="duplicate_stage",
					stage=stage_name,
					message=(
						f"stage {stage_name!r} is declared {count} times "
						f"on {spec.jtbd_id!r}"
					),
					fixhint="Remove the duplicate stage entries.",
					doc_url=_DOC_URL,
				))

		for required in self.required_stages:
			if required in direct:
				continue
			if required in delegations:
				delegate_id = delegations[required]
				delegate = bundle_index.get(delegate_id)
				if delegate is None:
					issues.append(Issue(
						severity="error",
						rule="stage_delegation_unresolved",
						stage=required,
						message=(
							f"stage {required!r} on {spec.jtbd_id!r} is "
							f"delegated to {delegate_id!r}, which is "
							f"not in the bundle"
						),
						fixhint=(
							"Add the delegate JTBD to the bundle or "
							"declare the stage directly."
						),
						related_jtbds=[delegate_id],
						doc_url=_DOC_URL,
					))
					continue
				if required not in delegate.stage_names():
					issues.append(Issue(
						severity="error",
						rule="stage_delegation_unfulfilled",
						stage=required,
						message=(
							f"stage {required!r} on {spec.jtbd_id!r} is "
							f"delegated to {delegate_id!r}, which does "
							f"not declare it"
						),
						fixhint=(
							f"Declare stage {required!r} on "
							f"{delegate_id!r} or change the delegation."
						),
						related_jtbds=[delegate_id],
						doc_url=_DOC_URL,
					))
				continue
			issues.append(Issue(
				severity="error",
				rule="missing_required_stage",
				stage=required,
				message=(
					f"required stage {required!r} is missing on "
					f"{spec.jtbd_id!r}"
				),
				fixhint=(
					f"Add a {required}-stage step or set "
					f"'{required}_handled_by: <other_jtbd_id>'."
				),
				doc_url=_DOC_URL,
			))

		if self.hint_optional:
			for optional in self.optional_stages:
				if optional in direct or optional in delegations:
					continue
				issues.append(Issue(
					severity="info",
					rule="optional_stage_recommended",
					stage=optional,
					message=(
						f"optional stage {optional!r} is recommended on "
						f"{spec.jtbd_id!r}"
					),
					fixhint=(
						f"Add a {optional}-stage step if compensation is "
						f"possible."
					),
					doc_url=_DOC_URL,
				))

		assert all(issue.rule for issue in issues), (
			"every issue must carry a stable rule id"
		)
		return issues


__all__ = ["LifecycleAnalyzer"]
