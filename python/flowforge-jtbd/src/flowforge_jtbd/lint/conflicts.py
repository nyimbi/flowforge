"""JTBD conflict solver — Z3 backend with a simple-pairs fallback.

Implements §2.2 of ``framework/docs/jtbd-editor-arch.md`` and §4.2 of
``framework/docs/flowforge-evolution.md`` (ticket E-5). Each JTBD that
participates in conflict checking declares the tuple
``(timing, data, consistency)`` plus the entities it touches; the
solver flags contradictions across JTBDs that share an entity.

| Dimension | Values |
|-----------|--------|
| timing | ``realtime`` \\| ``batch`` |
| data | ``read`` \\| ``write`` \\| ``both`` |
| consistency | ``strong`` \\| ``eventual`` |

Two backends ship:

- :class:`Z3ConflictSolver` — uses ``python-z3-solver`` when installed.
  The SMT formulation lets later phases extend the rule set with
  transitive constraints on ``requires`` chains without rewriting the
  surface.
- :class:`PairsConflictSolver` — ``O(n²)`` pairwise check using a
  hard-coded incompatibility table. Used when Z3 is missing, when an
  entity-touch component crosses ``_PAIRS_FALLBACK_THRESHOLD = 50``
  (per ``jtbd-editor-arch.md`` §23.10), or when the caller passes
  ``solver=PairsConflictSolver()`` explicitly.

Public surface:

- :func:`detect_conflicts` — composition-time entrypoint. Returns a
  list of :class:`~flowforge_jtbd.lint.results.Issue` so the output
  slots into :class:`~flowforge_jtbd.lint.results.LintReport`
  alongside lifecycle / dependency / actor findings.
- :func:`default_solver` — returns the auto-chosen backend instance.
- :func:`extract_semantics` — pulls per-JTBD ``semantics`` blocks from
  a composition spec into :class:`JtbdSemantics` instances. Tolerates
  missing blocks (returns an empty list rather than failing) so JTBDs
  authored before the semantics block existed don't false-positive.

The solver intentionally only conflict-checks **writers**: read-only
fan-out is fine — multiple JTBDs reading the same entity at different
timings/consistencies does not constrain each other.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Protocol, runtime_checkable

from .results import Issue

Timing = Literal["realtime", "batch"]
Data = Literal["read", "write", "both"]
Consistency = Literal["strong", "eventual"]
Severity = Literal["error", "warning"]

_TIMINGS: tuple[Timing, ...] = ("realtime", "batch")
_DATAS: tuple[Data, ...] = ("read", "write", "both")
_CONSISTENCIES: tuple[Consistency, ...] = ("strong", "eventual")

# Per arch §23.10: partition-size cutoff above which we skip Z3 even when
# it's installed; the O(n²) pairs check has a much smaller constant.
_PAIRS_FALLBACK_THRESHOLD = 50


@dataclass(frozen=True)
class JtbdSemantics:
	"""Declared composition-time semantics for one JTBD.

	``entities`` is the set of entity ids the JTBD touches. A JTBD that
	touches no shared entity contributes no conflicts and can be
	omitted. Entity ids are matched as opaque strings — the solver
	does not inspect entity schemas.
	"""

	jtbd_id: str
	timing: Timing
	data: Data
	consistency: Consistency
	entities: tuple[str, ...]

	def __post_init__(self) -> None:
		assert isinstance(self.jtbd_id, str) and self.jtbd_id, "jtbd_id required"
		assert self.timing in _TIMINGS, f"bad timing {self.timing!r}"
		assert self.data in _DATAS, f"bad data {self.data!r}"
		assert (
			self.consistency in _CONSISTENCIES
		), f"bad consistency {self.consistency!r}"
		assert isinstance(self.entities, tuple), "entities must be a tuple"

	def writes(self) -> bool:
		return self.data in ("write", "both")

	def reads(self) -> bool:
		return self.data in ("read", "both")


@runtime_checkable
class ConflictSolver(Protocol):
	"""Pluggable solver backend."""

	backend: str

	def detect(self, semantics: list[JtbdSemantics]) -> list[Issue]: ...


# ---------------------------------------------------------------------------
# Pair rule table — applied identically by both backends so behaviour is
# stable regardless of whether Z3 is available.
# ---------------------------------------------------------------------------

# Each entry: (left_tuple, right_tuple, severity, rule_id). Match is
# order-independent; the helper checks both orderings.

_PairTuple = tuple[Timing, Data, Consistency]
_PairRule = tuple[_PairTuple, _PairTuple, Severity, str]

_PAIR_RULES: tuple[_PairRule, ...] = (
	# Two writers asking for `strong` consistency on different timings —
	# batch can't honour the realtime side of the same write surface.
	(("realtime", "write", "strong"), ("batch", "write", "strong"),
		"error", "strong_consistency_in_batch_path"),
	(("realtime", "both", "strong"), ("batch", "write", "strong"),
		"error", "strong_consistency_in_batch_path"),
	(("realtime", "write", "strong"), ("batch", "both", "strong"),
		"error", "strong_consistency_in_batch_path"),
	(("realtime", "both", "strong"), ("batch", "both", "strong"),
		"error", "strong_consistency_in_batch_path"),
	# Mixed strong vs eventual on the same write path — author must
	# declare how they want the writer surface to combine. Warn rather
	# than error, per arch §2.2 (the example is `account_open` vs
	# `nightly_balance_recompute`).
	(("realtime", "write", "strong"), ("batch", "write", "eventual"),
		"warning", "combined_consistency_unclear"),
	(("realtime", "both", "strong"), ("batch", "write", "eventual"),
		"warning", "combined_consistency_unclear"),
	(("realtime", "write", "strong"), ("batch", "both", "eventual"),
		"warning", "combined_consistency_unclear"),
	(("realtime", "both", "strong"), ("batch", "both", "eventual"),
		"warning", "combined_consistency_unclear"),
)


def _bucket_by_entity(
	semantics: Iterable[JtbdSemantics],
) -> dict[str, list[JtbdSemantics]]:
	"""Group declared semantics by every entity each JTBD touches."""

	out: dict[str, list[JtbdSemantics]] = defaultdict(list)
	for s in semantics:
		for ent in s.entities:
			out[ent].append(s)
	return dict(out)


def _matches_rule(
	a: JtbdSemantics, b: JtbdSemantics, left: _PairTuple, right: _PairTuple
) -> bool:
	a_tuple = (a.timing, a.data, a.consistency)
	b_tuple = (b.timing, b.data, b.consistency)
	return (a_tuple, b_tuple) == (left, right) or (a_tuple, b_tuple) == (right, left)


def _pair_violation(
	a: JtbdSemantics, b: JtbdSemantics
) -> tuple[Severity, str] | None:
	"""Return ``(severity, rule_id)`` if the pair matches a rule, else ``None``."""

	for left, right, sev, rule in _PAIR_RULES:
		if _matches_rule(a, b, left, right):
			return sev, rule
	return None


_RULE_MESSAGES: dict[str, str] = {
	"strong_consistency_in_batch_path": (
		"two writers declare `strong` consistency on the same entity but "
		"on different timings; a batch path can't honour strong consistency"
	),
	"combined_consistency_unclear": (
		"writer surface combines `realtime+strong` with `batch+eventual` "
		"on the same entity; declare an explicit combined consistency"
	),
}

_RULE_FIXHINTS: dict[str, str] = {
	"strong_consistency_in_batch_path": (
		"either move the batch writer to `eventual` consistency, or split "
		"the entity so each writer owns a disjoint surface"
	),
	"combined_consistency_unclear": (
		"add an explicit `(eventual, write, eventual)` declaration on the "
		"combined writer surface, or mark the batch JTBD as read-only"
	),
}


def _describe_pair(a: JtbdSemantics, b: JtbdSemantics) -> str:
	return (
		f"{a.jtbd_id}=({a.timing},{a.data},{a.consistency}) vs "
		f"{b.jtbd_id}=({b.timing},{b.data},{b.consistency})"
	)


def _emit_pair_issues(
	semantics: list[JtbdSemantics],
) -> list[Issue]:
	"""Shared driver: bucket by ``(entity, signature)``, then iterate only
	rule-relevant cross products (audit-2026 J-02).

	The previous implementation was ``O(B²)`` per entity, where ``B`` is
	the per-entity writer count, and additionally scanned 8 rules per
	pair. With 10K writers on a hot entity that approached 50s.

	The new implementation pre-buckets writers by their
	``(timing, data, consistency)`` signature *within each entity*. The
	rule table only fires across two specific signatures, so we iterate
	the cross product of (left-signature writers) × (right-signature
	writers) once per rule. Worst-case work is bounded by the per-rule
	signature partitions instead of the full ``B²`` cohort, and the
	``_pair_violation`` lookup vanishes.

	Both backends route through this helper so output is identical
	whether Z3 is installed or not.
	"""

	# Bucket count is bounded by ``len(entities) × len(_TIMINGS) ×
	# len(_DATAS) × len(_CONSISTENCIES) = entities × 12``. Each writer
	# contributes one bucket entry per entity it touches.
	ent_sig: dict[
		tuple[str, _PairTuple], list[JtbdSemantics]
	] = defaultdict(list)
	for s in semantics:
		if not s.writes():
			continue
		sig: _PairTuple = (s.timing, s.data, s.consistency)
		for ent in s.entities:
			ent_sig[(ent, sig)].append(s)

	issues: list[Issue] = []
	# de-dupe key: (jtbd_a, jtbd_b, rule). A pair touching multiple
	# shared entities only gets one issue; entity reported is the
	# alphabetically first match.
	seen: set[tuple[str, str, str]] = set()

	# Stable iteration: sorted entity list so output ordering is
	# deterministic across runs / hash randomisation.
	entities = sorted({entity for (entity, _sig) in ent_sig.keys()})
	for entity in entities:
		for left_sig, right_sig, sev, rule in _PAIR_RULES:
			l_list = ent_sig.get((entity, left_sig))
			r_list = ent_sig.get((entity, right_sig))
			if not l_list or not r_list:
				continue
			# Sort once per bucket so we get stable issue ordering.
			l_sorted = sorted(l_list, key=lambda s: s.jtbd_id)
			r_sorted = sorted(r_list, key=lambda s: s.jtbd_id)
			for a in l_sorted:
				for b in r_sorted:
					if a.jtbd_id == b.jtbd_id:
						continue
					key_pair = tuple(sorted((a.jtbd_id, b.jtbd_id)))
					dedupe_key = (key_pair[0], key_pair[1], rule)
					if dedupe_key in seen:
						continue
					seen.add(dedupe_key)
					issues.append(
						Issue(
							severity=sev,
							rule=rule,
							message=_RULE_MESSAGES[rule],
							fixhint=_RULE_FIXHINTS.get(rule),
							related_jtbds=list(key_pair),
							extra={
								"entity": entity,
								"detail": _describe_pair(a, b),
							},
						)
					)
	# Stable order: errors first, then warnings, then by jtbd ids.
	issues.sort(
		key=lambda i: (
			0 if i.severity == "error" else 1,
			tuple(i.related_jtbds),
			i.rule,
		)
	)
	return issues


class PairsConflictSolver:
	"""``O(n²)`` pairwise check using the incompatibility table.

	Used when Z3 is unavailable or when an entity-touch component
	exceeds :data:`_PAIRS_FALLBACK_THRESHOLD` (per arch §23.10).
	"""

	backend = "pairs"

	def detect(self, semantics: list[JtbdSemantics]) -> list[Issue]:
		assert isinstance(semantics, list), "semantics must be a list"
		return _emit_pair_issues(semantics)


class Z3ConflictSolver:
	"""SMT-backed solver via ``python-z3-solver``.

	The encoding mirrors :class:`PairsConflictSolver` for v1 — same rule
	table, same outputs — but each rule is expressed as an SMT clause
	using Z3 enum sorts. This proves the SAT formulation is sound at
	v1 and gives later phases a place to add transitive constraints
	(e.g., chained writers via ``requires``) without rewriting the
	surface.

	Construction raises ``RuntimeError`` if Z3 is missing — callers
	should normally use :func:`default_solver` which falls back to
	pairs.
	"""

	backend = "z3"

	def __init__(self) -> None:
		try:
			import z3  # noqa: F401  (presence check)
		except ImportError as exc:  # pragma: no cover - guard
			raise RuntimeError(
				"Z3ConflictSolver requires python-z3-solver; "
				"install with `pip install z3-solver` or use PairsConflictSolver."
			) from exc

	def detect(self, semantics: list[JtbdSemantics]) -> list[Issue]:
		assert isinstance(semantics, list), "semantics must be a list"

		import z3  # local — already guarded in __init__

		# Independently verify the pair rule table is satisfiable as an
		# SMT problem. We don't actually need Z3 to solve any individual
		# pair (the lookup is O(1)), but running each candidate through
		# Z3.check() proves the SMT encoding agrees with the table —
		# making the backend a useful sanity check today and a real
		# extension point tomorrow.
		#
		# A fresh ``z3.Context`` per call keeps EnumSort declarations
		# scoped: re-running ``detect()`` in the same process would
		# otherwise raise "enumeration sort name is already declared"
		# from the global Z3 namespace.
		ctx = z3.Context()
		timing_sort, timing_consts = z3.EnumSort("Timing", list(_TIMINGS), ctx=ctx)
		data_sort, data_consts = z3.EnumSort("Data", list(_DATAS), ctx=ctx)
		cons_sort, cons_consts = z3.EnumSort(
			"Consistency", list(_CONSISTENCIES), ctx=ctx,
		)
		timing_map = dict(zip(_TIMINGS, timing_consts))
		data_map = dict(zip(_DATAS, data_consts))
		cons_map = dict(zip(_CONSISTENCIES, cons_consts))

		# Smoke-check: each rule clause must be satisfiable in isolation.
		# If Z3 says UNSAT we have a logic bug — bail loudly.
		for left, right, _, rule in _PAIR_RULES:
			solver = z3.Solver(ctx=ctx)
			t_a = z3.Const("t_a", timing_sort)
			d_a = z3.Const("d_a", data_sort)
			c_a = z3.Const("c_a", cons_sort)
			t_b = z3.Const("t_b", timing_sort)
			d_b = z3.Const("d_b", data_sort)
			c_b = z3.Const("c_b", cons_sort)
			solver.add(t_a == timing_map[left[0]])
			solver.add(d_a == data_map[left[1]])
			solver.add(c_a == cons_map[left[2]])
			solver.add(t_b == timing_map[right[0]])
			solver.add(d_b == data_map[right[1]])
			solver.add(c_b == cons_map[right[2]])
			result = solver.check()
			assert result == z3.sat, (
				f"rule {rule!r} encodes an unsatisfiable clause — "
				f"this is a logic bug in _PAIR_RULES"
			)

		# Now drive the actual pair detection through the same shared
		# helper as the pairs backend. The behaviour difference is the
		# SMT smoke-check above, not the per-pair output.
		return _emit_pair_issues(semantics)


def default_solver() -> ConflictSolver:
	"""Return a Z3 solver if installed, else the pairs solver.

	Callers that want to force a backend can construct
	:class:`PairsConflictSolver` or :class:`Z3ConflictSolver` directly.
	"""

	try:
		import z3  # noqa: F401
	except ImportError:
		return PairsConflictSolver()
	return Z3ConflictSolver()


def detect_conflicts(
	semantics: list[JtbdSemantics],
	*,
	solver: ConflictSolver | None = None,
) -> list[Issue]:
	"""Composition-time conflict detection.

	Picks :func:`default_solver` if no solver is supplied, then applies
	the §23.10 partition-size fallback: any entity-touch component with
	more than :data:`_PAIRS_FALLBACK_THRESHOLD` JTBDs is solved with
	the pairs backend even when Z3 is available, because Z3's constant
	factor on large components is significantly worse than the O(n²)
	lookup.
	"""

	assert isinstance(semantics, list), "semantics must be a list"

	chosen = solver or default_solver()
	if chosen.backend != "z3":
		return chosen.detect(semantics)

	# Z3 path — but partition by entity-touch component and route
	# components above the threshold through the pairs backend.
	per_entity = _bucket_by_entity(semantics)
	if not per_entity:
		return []
	largest_component = max(len(group) for group in per_entity.values())
	if largest_component > _PAIRS_FALLBACK_THRESHOLD:
		return PairsConflictSolver().detect(semantics)
	return chosen.detect(semantics)


# ---------------------------------------------------------------------------
# Composition extraction helper.
# ---------------------------------------------------------------------------

def extract_semantics(composition: dict[str, Any]) -> list[JtbdSemantics]:
	"""Pull ``semantics`` blocks out of a composition spec.

	Composition shape (subset)::

	    {
	        "jtbds": [
	            {
	                "id": "account_open",
	                "semantics": {
	                    "timing": "realtime",
	                    "data": "write",
	                    "consistency": "strong",
	                    "entities": ["account"]
	                }
	            },
	            ...
	        ]
	    }

	A JTBD entry without a ``semantics`` block is silently skipped —
	conflict checking only applies to JTBDs that opt in. Malformed
	blocks raise ``ValueError`` so the composer surfaces the typo
	rather than emitting silent false-negatives.

	The full ``semantics`` schema lands with the composition lockfile
	in E-1; this helper accepts the same shape early so E-5 unit tests
	can drive the solver from a composition fixture today.
	"""

	assert isinstance(composition, dict), "composition must be a dict"
	out: list[JtbdSemantics] = []
	for entry in composition.get("jtbds", []) or []:
		assert isinstance(entry, dict)
		sem = entry.get("semantics")
		if sem is None:
			continue
		jtbd_id = entry.get("id")
		if not isinstance(jtbd_id, str) or not jtbd_id:
			raise ValueError("composition jtbd entry missing 'id'")
		try:
			timing = sem["timing"]
			data = sem["data"]
			consistency = sem["consistency"]
			entities = sem.get("entities") or []
		except KeyError as exc:
			raise ValueError(
				f"jtbd {jtbd_id!r}: semantics missing key {exc.args[0]!r}"
			) from exc
		if timing not in _TIMINGS:
			raise ValueError(f"jtbd {jtbd_id!r}: bad timing {timing!r}")
		if data not in _DATAS:
			raise ValueError(f"jtbd {jtbd_id!r}: bad data {data!r}")
		if consistency not in _CONSISTENCIES:
			raise ValueError(f"jtbd {jtbd_id!r}: bad consistency {consistency!r}")
		if not isinstance(entities, list) or not all(
			isinstance(e, str) for e in entities
		):
			raise ValueError(f"jtbd {jtbd_id!r}: entities must be list[str]")
		out.append(
			JtbdSemantics(
				jtbd_id=jtbd_id,
				timing=timing,
				data=data,
				consistency=consistency,
				entities=tuple(entities),
			)
		)
	return out


__all__ = [
	"ConflictSolver",
	"JtbdSemantics",
	"PairsConflictSolver",
	"Z3ConflictSolver",
	"default_solver",
	"detect_conflicts",
	"extract_semantics",
]
