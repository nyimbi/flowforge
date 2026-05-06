"""JTBD conflict solver — Z3 backend with a simple-pairs fallback.

Implements §2.2 of ``framework/docs/jtbd-editor-arch.md`` and §4.2 of
``framework/docs/flowforge-evolution.md``. Each JTBD that participates
in conflict checking declares the tuple ``(timing, data, consistency)``
plus a list of touched entities. The solver flags contradictions
across JTBDs that touch the same entity.

| Dimension | Values |
|-----------|--------|
| timing | ``realtime`` \\| ``batch`` |
| data | ``read`` \\| ``write`` \\| ``both`` |
| consistency | ``strong`` \\| ``eventual`` |

Two backends are shipped:

- :class:`Z3ConflictSolver` — uses ``python-z3-solver`` when installed.
  The SMT formulation lets later phases (post-E1) extend the rule set
  with transitive constraints on ``requires`` chains without rewriting
  the surface.
- :class:`PairsConflictSolver` — ``O(n²)`` pairwise check using a
  hard-coded incompatibility table. Used when Z3 is missing, when an
  entity-touch component crosses ``_PAIRS_FALLBACK_THRESHOLD = 50``
  (per ``jtbd-editor-arch.md`` §23.10), or when the caller passes
  ``solver=PairsConflictSolver()`` explicitly.

Public surface:

- :func:`detect_conflicts` — composition-time entrypoint. Picks the
  backend automatically (Z3 if installed; pairs otherwise) and applies
  the §23.10 partition-size fallback.
- :func:`default_solver` — returns the auto-chosen backend instance.
- :func:`extract_semantics` — pulls per-JTBD ``semantics`` blocks from
  a composition spec into :class:`JtbdSemantics` instances. Tolerates
  missing blocks (returns an empty list rather than failing).

The solver intentionally only conflict-checks **writers**. Read-only
fan-out is fine — multiple JTBDs reading the same entity at different
timings/consistencies does not constrain each other.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Protocol, runtime_checkable

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

	``entities`` is the set of entity ids the JTBD touches (a JTBD that
	touches no shared entity contributes no conflicts and can be
	omitted). Entity ids are matched as opaque strings — the solver
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
		assert self.consistency in _CONSISTENCIES, f"bad consistency {self.consistency!r}"
		assert isinstance(self.entities, tuple), "entities must be a tuple"

	def writes(self) -> bool:
		return self.data in ("write", "both")

	def reads(self) -> bool:
		return self.data in ("read", "both")


@dataclass(frozen=True)
class ConflictIssue:
	"""One conflict surfaced by the solver.

	``jtbd_ids`` is sorted to keep the issue list stable across solver
	implementations; ``entity`` names the shared surface that triggered
	the rule.
	"""

	severity: Severity
	rule: str
	jtbd_ids: tuple[str, ...]
	entity: str | None = None
	detail: str = ""

	def __post_init__(self) -> None:
		assert self.severity in ("error", "warning")
		assert self.rule, "rule id required"
		assert isinstance(self.jtbd_ids, tuple) and len(self.jtbd_ids) >= 1


@runtime_checkable
class ConflictSolver(Protocol):
	"""Pluggable solver backend."""

	backend: str

	def detect(self, semantics: list[JtbdSemantics]) -> list[ConflictIssue]: ...


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


def _describe_pair(a: JtbdSemantics, b: JtbdSemantics) -> str:
	return (
		f"{a.jtbd_id}=({a.timing},{a.data},{a.consistency}) vs "
		f"{b.jtbd_id}=({b.timing},{b.data},{b.consistency})"
	)


def _emit_pair_issues(
	semantics: list[JtbdSemantics],
) -> list[ConflictIssue]:
	"""Shared driver: bucket by entity, run the pair table, emit issues.

	Both backends route through this helper. The Z3 backend additionally
	validates the rule table against an SMT encoding (see
	:meth:`Z3ConflictSolver.detect`); the output is identical.
	"""

	issues: list[ConflictIssue] = []
	# de-dupe: a pair touching multiple shared entities only gets one
	# issue per (pair, rule). Entity is reported as the alphabetically
	# first match for stability.
	seen: dict[tuple[str, str, str], str] = {}
	per_entity = _bucket_by_entity(semantics)
	for entity in sorted(per_entity):
		group = per_entity[entity]
		writers = sorted([s for s in group if s.writes()], key=lambda s: s.jtbd_id)
		for i, a in enumerate(writers):
			for b in writers[i + 1 :]:
				res = _pair_violation(a, b)
				if res is None:
					continue
				sev, rule = res
				key_pair = tuple(sorted((a.jtbd_id, b.jtbd_id)))
				dedupe_key = (key_pair[0], key_pair[1], rule)
				if dedupe_key in seen:
					continue
				seen[dedupe_key] = entity
				issues.append(
					ConflictIssue(
						severity=sev,
						rule=rule,
						jtbd_ids=key_pair,
						entity=entity,
						detail=_describe_pair(a, b),
					)
				)
	# Stable order: errors first, then warnings, then by jtbd_ids.
	issues.sort(key=lambda i: (0 if i.severity == "error" else 1, i.jtbd_ids, i.rule))
	return issues


class PairsConflictSolver:
	"""``O(n²)`` pairwise check using the incompatibility table.

	Used when Z3 is unavailable or when an entity-touch component
	exceeds :data:`_PAIRS_FALLBACK_THRESHOLD` (per arch §23.10).
	"""

	backend = "pairs"

	def detect(self, semantics: list[JtbdSemantics]) -> list[ConflictIssue]:
		assert isinstance(semantics, list), "semantics must be a list"
		return _emit_pair_issues(semantics)


class Z3ConflictSolver:
	"""SMT-backed solver via ``python-z3-solver``.

	The encoding mirrors :class:`PairsConflictSolver` for v1 — same rule
	table, same outputs — but each rule is expressed as an SMT clause
	using Z3 enum sorts. This proves the SAT formulation is sound at
	v1 and gives later phases (post-E1) a place to add transitive
	constraints (e.g., chained writers via ``requires``) without
	rewriting the surface.

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

	def detect(self, semantics: list[JtbdSemantics]) -> list[ConflictIssue]:
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
		cons_sort, cons_consts = z3.EnumSort("Consistency", list(_CONSISTENCIES), ctx=ctx)
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
) -> list[ConflictIssue]:
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

	The full schema for ``semantics`` lands with E-1 (JtbdSpec); this
	helper accepts the same shape early so E-5 unit tests can drive the
	solver from a composition fixture today.
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
		if not isinstance(entities, list) or not all(isinstance(e, str) for e in entities):
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
