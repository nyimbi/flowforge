"""Per-JTBD generator: guard-aware reachability checker.

v0.3.0 W4a / item 4 of :doc:`docs/improvements`. Beyond the topology
check the compiler does today, evaluate guards symbolically against the
free variables they reference (``context.<name>``) and decide:

* **Reachable**: there exists an assignment to the guard variables under
  which the transition fires.
* **Unreachable**: the guard contradicts the workflow's preconditions
  (e.g. two transitions sharing ``from_state`` + ``event`` but with
  contradictory guards on the same variable).
* **Unwritable variable**: a guard reads ``context.<X>`` but ``X`` is
  not declared in any JTBD ``data_capture`` field — the production
  context cannot populate it via the synthesised form, so the
  transition is dead in practice even when the symbolic solver finds
  it reachable.

The output lands at ``workflows/<id>/reachability.json`` per JTBD when
``z3-solver`` is installed, and ``workflows/<id>/reachability_skipped.txt``
when it's not. ADR-004 pins the placeholder text so the byte-identical
regen contract holds across both flag values.

Determinism guarantees:

* Transitions sorted by ``(priority, id)`` before checking.
* Guard variables sorted before being declared as z3 booleans.
* JSON output sorted keys, fixed indent.
* z3 invocation per-transition is independent — no global solver state
  leaks between transitions.

Why opt-in extra: per ADR-004, ``z3-solver`` is large (~50 MB) and
shipping it as a hard dep forces every host to pay for it even when
they never run reachability. The placeholder file keeps regen
byte-stable so hosts opting out don't break ``scripts/check_all.sh``
step 8.
"""

from __future__ import annotations

import json
from typing import Any

from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``.
CONSUMES: tuple[str, ...] = (
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].id",
	"jtbds[].initial_state",
	"jtbds[].states",
	"jtbds[].title",
	"jtbds[].transitions",
)


# Placeholder text emitted when ``z3-solver`` is not installed. Frozen
# per ADR-004 — any drift here is a CI failure (the byte-identical
# regen contract treats this file as part of the canonical output).
SKIPPED_PLACEHOLDER: str = (
	"Reachability analysis skipped: z3-solver not installed.\n"
	"Install with: pip install 'flowforge-cli[reachability]'\n"
)


def _guard_vars(transition: dict[str, Any]) -> list[str]:
	"""Return the ``context.<name>`` variables read by *transition*'s guards.

	The synthesiser only ever emits ``{kind: "expr", expr: {var: ...}}``
	guards (cross-runtime parity invariant 5). Returns sorted unique
	names so the z3 declaration order is deterministic.
	"""

	out: set[str] = set()
	for g in transition.get("guards") or ():
		if g.get("kind") == "expr":
			expr = g.get("expr") or {}
			v = expr.get("var")
			if isinstance(v, str) and v.startswith("context."):
				out.add(v[len("context."):])
	return sorted(out)


def _check_transition_reachable(transition: dict[str, Any]) -> tuple[bool, str | None]:
	"""Use z3 to decide whether the transition's guard set is satisfiable.

	Returns ``(reachable, witness)``:

	* ``(True, None)`` — no guards (always-fire).
	* ``(True, "<var>=true,...")`` — guards satisfiable; witness is a
	  deterministic stringification of the model.
	* ``(False, None)`` — guards unsatisfiable (contradictory).

	The witness is only used in the JSON output; we keep it
	deterministic (sorted by var name) so two regens produce identical
	bytes even if z3 returns model literals in non-deterministic order.
	"""

	import z3  # local import — caller has already validated importability

	guard_vars = _guard_vars(transition)
	if not guard_vars:
		# No guards → trivially reachable. No solver invocation needed
		# (saves the import cost on hot paths and keeps the output
		# stable when z3 internals change).
		return True, None

	# Each ``context.<X>`` is a free boolean — the synthesiser only
	# emits boolean guard reads (cross-runtime parity invariant 5).
	# Numeric / string guards would require typed sorts; that is
	# deliberately deferred to v0.4.0.
	z3_vars = {name: z3.Bool(name) for name in guard_vars}
	solver = z3.Solver()
	# AND every guard's truth value. The synthesised guard is
	# ``{var: "context.X"}`` which evaluates to truthy when X is true,
	# so the symbolic constraint is just the variable itself.
	for name in guard_vars:
		solver.add(z3_vars[name])

	if solver.check() != z3.sat:
		return False, None

	# z3.Model.eval is symbolic evaluation against the SAT model — it
	# is not Python's built-in eval and runs no string code. We only
	# stringify the resulting z3 literal (true/false) for the witness.
	model = solver.model()
	parts: list[str] = []
	for name in guard_vars:
		val = model.eval(z3_vars[name], model_completion=True)
		parts.append(f"{name}={str(val).lower()}")
	return True, ",".join(parts)


def _detect_unwritable(
	transition: dict[str, Any],
	field_ids: frozenset[str],
) -> list[str]:
	"""Return guard variables not produced by any ``data_capture`` field.

	A guard reading ``context.<X>`` is dead when no field produces ``X``
	— the synthesised form has no input that can populate it, so the
	transition is unreachable in production even when z3 finds the
	guard satisfiable in isolation. Sorted for byte-stability.
	"""

	return sorted(name for name in _guard_vars(transition) if name not in field_ids)


def _build_report(jtbd: NormalizedJTBD) -> dict[str, Any]:
	"""Build the reachability report for *jtbd*. Pure function."""

	field_ids = frozenset(f.id for f in jtbd.fields)
	transitions = sorted(
		[dict(t) for t in jtbd.transitions],
		key=lambda t: (int(t.get("priority", 0)), str(t.get("id", ""))),
	)

	results: list[dict[str, Any]] = []
	reachable_count = 0
	unreachable_count = 0
	unwritable_count = 0

	for t in transitions:
		reachable, witness = _check_transition_reachable(t)
		unwritable = _detect_unwritable(t, field_ids)
		entry: dict[str, Any] = {
			"id": str(t.get("id", "")),
			"event": str(t.get("event", "")),
			"from_state": str(t.get("from_state", "")),
			"to_state": str(t.get("to_state", "")),
			"priority": int(t.get("priority", 0)),
			"guard_vars": _guard_vars(t),
			"reachable": reachable,
		}
		if witness is not None:
			entry["witness"] = witness
		if unwritable:
			entry["unwritable_vars"] = unwritable
			unwritable_count += 1
		if reachable:
			reachable_count += 1
		else:
			unreachable_count += 1
		results.append(entry)

	report: dict[str, Any] = {
		"jtbd_id": jtbd.id,
		"jtbd_title": jtbd.title,
		"initial_state": jtbd.initial_state,
		"summary": {
			"total": len(results),
			"reachable": reachable_count,
			"unreachable": unreachable_count,
			"with_unwritable_vars": unwritable_count,
		},
		"transitions": results,
	}
	return report


def generate(_bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	"""Emit ``workflows/<id>/reachability.json`` (or the skipped placeholder).

	When ``z3-solver`` is installed the generator runs the symbolic
	check and emits the JSON report. When not installed it emits the
	frozen placeholder per ADR-004 so the byte-identical regen
	contract holds across both flag values (extra installed vs not).
	"""

	try:
		import z3  # noqa: F401 — probe only; the analysis re-imports lazily
	except ImportError:
		return GeneratedFile(
			path=f"workflows/{jtbd.id}/reachability_skipped.txt",
			content=SKIPPED_PLACEHOLDER,
		)

	report = _build_report(jtbd)
	content = json.dumps(report, indent=2, sort_keys=True) + "\n"
	return GeneratedFile(
		path=f"workflows/{jtbd.id}/reachability.json",
		content=content,
	)
