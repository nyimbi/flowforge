"""Actor consistency analyzer.

Per ``framework/docs/jtbd-editor-arch.md`` §2.4:

- Same role acting in conflicting capacities (e.g., creator AND
  approver of the same entity in the same context) → ``warning``.
- Spec requires ``actor.tier=N``, but the role's ``shared.roles``
  default tier is below ``N`` → ``error``.
- Spec references a role not declared in ``shared.roles`` → ``warning``
  (a missing declaration is a frequent author oversight, but not a
  hard fail because some hosts populate roles from external sources).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..spec import JtbdBundle
from .results import Issue


_DOC_URL = "/docs/jtbd-editor#actor-consistency"


# Capacity pairs that are considered conflicting on the same context.
# This is the canonical seed; per-domain packs may extend.
_CONFLICTING_CAPACITY_PAIRS: frozenset[frozenset[str]] = frozenset({
	frozenset({"creator", "approver"}),
	frozenset({"submitter", "approver"}),
	frozenset({"requester", "approver"}),
	frozenset({"author", "reviewer"}),
})


@dataclass
class ActorConsistencyAnalyzer:
	"""Per-bundle actor consistency check.

	Stateful only across one ``analyze`` call — safe to share an
	instance across bundles.
	"""

	conflicting_capacity_pairs: frozenset[frozenset[str]] = field(
		default_factory=lambda: _CONFLICTING_CAPACITY_PAIRS,
	)

	def analyze(
		self,
		bundle: JtbdBundle,
	) -> dict[str, list[Issue]]:
		"""Return a mapping of ``jtbd_id -> issues``.

		Empty entries are omitted, so callers can iterate the result
		safely.
		"""
		issues_by_spec: dict[str, list[Issue]] = {}

		# Pass 1: per-spec checks (unknown-role, tier authority).
		for spec in bundle.jtbds:
			actor = spec.actor
			if actor is None:
				continue
			role_def = bundle.shared_roles.get(actor.role)
			if role_def is None:
				issues_by_spec.setdefault(spec.jtbd_id, []).append(Issue(
					severity="warning",
					rule="actor_role_undeclared",
					role=actor.role,
					message=(
						f"role {actor.role!r} on {spec.jtbd_id!r} is not "
						f"declared in bundle.shared_roles"
					),
					fixhint=(
						"Declare the role in the bundle's shared.roles "
						"or remove the reference."
					),
					doc_url=_DOC_URL,
				))
				continue
			if actor.tier is not None and actor.tier > role_def.default_tier:
				issues_by_spec.setdefault(spec.jtbd_id, []).append(Issue(
					severity="error",
					rule="actor_authority_insufficient",
					role=actor.role,
					context=actor.context,
					message=(
						f"{spec.jtbd_id!r} requires tier={actor.tier} "
						f"but role {actor.role!r} default_tier="
						f"{role_def.default_tier}"
					),
					fixhint=(
						f"Either raise role {actor.role!r}'s default_tier "
						f"to {actor.tier} or assign a different role."
					),
					extra={
						"required_tier": actor.tier,
						"actual_tier": role_def.default_tier,
					},
					doc_url=_DOC_URL,
				))

		# Pass 2: cross-spec capacity-conflict scan. Group references
		# by ``(role, context)`` and flag any pair of capacities that
		# falls inside ``conflicting_capacity_pairs``.
		grouped = self._group_capacities(bundle)
		for (role, context), assignments in grouped.items():
			capacities = sorted({a.capacity for a in assignments if a.capacity})
			if len(capacities) < 2:
				continue
			conflict_pairs = self._conflicting_subsets(capacities)
			if not conflict_pairs:
				continue
			# Attach the warning to every involved JTBD so the editor
			# surfaces it on each card.
			involved_ids = sorted({a.jtbd_id for a in assignments})
			for pair in conflict_pairs:
				message = (
					f"role {role!r} acts as {sorted(pair)[0]!r} and "
					f"{sorted(pair)[1]!r} in context {context!r}"
				)
				for jtbd_id in involved_ids:
					issues_by_spec.setdefault(jtbd_id, []).append(Issue(
						severity="warning",
						rule="actor_role_conflict",
						role=role,
						context=context,
						message=message,
						fixhint=(
							"Split conflicting capacities into distinct "
							"roles, or scope each capacity to its own "
							"context."
						),
						related_jtbds=[i for i in involved_ids if i != jtbd_id],
						extra={"capacities": sorted(pair)},
						doc_url=_DOC_URL,
					))

		return issues_by_spec

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------
	def _group_capacities(
		self,
		bundle: JtbdBundle,
	) -> dict[tuple[str, str], list["_Assignment"]]:
		"""Group every ``(role, context)`` pair across the bundle.

		If ``actor.context`` is unset, falls back to the spec's
		``jtbd_id`` so we don't accidentally collapse across different
		bounded contexts.
		"""
		grouped: dict[tuple[str, str], list[_Assignment]] = {}
		for spec in bundle.jtbds:
			actor = spec.actor
			if actor is None:
				continue
			context = actor.context or spec.jtbd_id
			key = (actor.role, context)
			grouped.setdefault(key, []).append(_Assignment(
				jtbd_id=spec.jtbd_id,
				capacity=actor.capacity,
			))
		return grouped

	def _conflicting_subsets(
		self,
		capacities: list[str],
	) -> list[frozenset[str]]:
		hits: list[frozenset[str]] = []
		seen: set[frozenset[str]] = set()
		for i, left in enumerate(capacities):
			for right in capacities[i + 1:]:
				pair = frozenset({left, right})
				if pair in self.conflicting_capacity_pairs and pair not in seen:
					seen.add(pair)
					hits.append(pair)
		return hits


@dataclass(frozen=True)
class _Assignment:
	jtbd_id: str
	capacity: str | None


__all__ = ["ActorConsistencyAnalyzer"]
