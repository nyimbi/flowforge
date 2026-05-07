"""Workflow definition validator.

Per portability §10.3 example output, the validator checks:

* JSON schema (via :mod:`jsonschema`)
* unreachable states
* dead-end transitions (referencing missing states)
* duplicate priorities for the same (from_state, event)
* lookup-permission gating (every lookup mentions a permission gate)
* sub-workflow cycles
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..dsl import WorkflowDef
from ..expr import check_arity


class ValidationError(Exception):
	"""Raised by ``validate(strict=True)`` on the first issue."""


@dataclass
class ValidationReport:
	errors: list[str] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)

	@property
	def ok(self) -> bool:
		return not self.errors


_WD_SCHEMA: dict[str, Any] | None = None


def _wd_schema() -> dict[str, Any]:
	global _WD_SCHEMA
	if _WD_SCHEMA is None:
		try:
			res = files("flowforge.dsl.schema").joinpath("workflow_def.schema.json")
			_WD_SCHEMA = json.loads(res.read_text())
		except (ModuleNotFoundError, FileNotFoundError):
			# Fallback for editable installs where importlib.resources misses package data.
			here = Path(__file__).resolve().parent.parent / "dsl" / "schema" / "workflow_def.schema.json"
			_WD_SCHEMA = json.loads(here.read_text())
	assert _WD_SCHEMA is not None
	return _WD_SCHEMA


def _check_schema(data: dict[str, Any], report: ValidationReport) -> None:
	validator = Draft202012Validator(_wd_schema())
	for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
		path = "/".join(str(p) for p in err.absolute_path) or "<root>"
		report.errors.append(f"schema at {path}: {err.message}")


def _check_state_topology(wd: WorkflowDef, report: ValidationReport) -> None:
	state_names = {s.name for s in wd.states}
	if wd.initial_state not in state_names:
		report.errors.append(f"initial_state {wd.initial_state!r} not declared in states")

	# dead-end: transitions referencing missing states
	for t in wd.transitions:
		if t.from_state not in state_names:
			report.errors.append(f"transition {t.id}: from_state {t.from_state!r} not declared")
		if t.to_state not in state_names:
			report.errors.append(f"transition {t.id}: to_state {t.to_state!r} not declared")

	# unreachable: BFS from initial_state
	reachable = {wd.initial_state}
	graph: dict[str, list[str]] = defaultdict(list)
	for t in wd.transitions:
		graph[t.from_state].append(t.to_state)
	frontier = [wd.initial_state]
	while frontier:
		cur = frontier.pop()
		for nxt in graph.get(cur, ()):
			if nxt not in reachable:
				reachable.add(nxt)
				frontier.append(nxt)
	for s in wd.states:
		if s.name not in reachable and s.kind not in ("terminal_success", "terminal_fail"):
			report.errors.append(f"unreachable state {s.name!r}")
		# Allow terminals only if reachable
		if s.kind in ("terminal_success", "terminal_fail") and s.name not in reachable:
			report.errors.append(f"unreachable terminal {s.name!r}")


def _check_priorities(wd: WorkflowDef, report: ValidationReport) -> None:
	bucket: dict[tuple[str, str], dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
	for t in wd.transitions:
		bucket[(t.from_state, t.event)][t.priority].append(t.id)
	for (state, event), prio_map in bucket.items():
		for prio, ids in prio_map.items():
			if len(ids) > 1:
				report.errors.append(
					f"duplicate priority {prio} for ({state!r}, {event!r}): {ids}"
				)


def _check_subworkflow_cycle(wd: WorkflowDef, report: ValidationReport) -> None:
	# A simple check: no state with kind=subworkflow may name itself.
	for s in wd.states:
		if s.kind == "subworkflow" and s.subworkflow_key == wd.key:
			report.errors.append(f"subworkflow cycle: {s.name!r} -> {wd.key!r}")


def _check_expr_arity(wd: WorkflowDef, report: ValidationReport) -> None:
	"""Compile-time arity check for guard / effect expressions (audit-2026 C-07).

	Walks every ``Guard.expr`` and ``Effect.expr`` and surfaces operator
	calls with the wrong arity. Pairing this with the frozen registry
	(C-06) gives us replay determinism and prevents wrong-arity calls
	from reaching the engine at runtime.
	"""

	for t in wd.transitions:
		for i, g in enumerate(t.guards):
			path = f"transition {t.id!r}.guards[{i}].expr"
			report.errors.extend(check_arity(g.expr, path=path))
		for i, e in enumerate(t.effects):
			if e.expr is None:
				continue
			path = f"transition {t.id!r}.effects[{i}].expr"
			report.errors.extend(check_arity(e.expr, path=path))


def _expr_invokes_lookup(expr: Any) -> bool:
	"""Walk an expression AST and return True iff any node *invokes* a
	``lookup`` operator (or a ``var`` reference under ``lookup.*``).

	E-39 / C-10: this replaces the previous ``"lookup" in json.dumps(...)``
	substring heuristic, which would falsely flag an unrelated string
	literal like ``"lookup_failed"`` and emit a misleading
	permission-gate warning.

	The walker only looks at *operator names* (the single-key dict head)
	and ``var: lookup.*`` paths — string-literal payloads and value
	positions are ignored.
	"""

	if isinstance(expr, dict):
		# Operator dict: single-key {op: args}. The op name is the key.
		if len(expr) == 1:
			(op, arg), = expr.items()
			if op == "lookup":
				return True
			if op == "var" and isinstance(arg, str) and arg.startswith("lookup."):
				return True
			# Recurse into the args (values, lists, nested dicts).
			return _expr_invokes_lookup(arg)
		# Multi-key dict (rare; usually a parsed object literal). Walk values.
		return any(_expr_invokes_lookup(v) for v in expr.values())
	if isinstance(expr, list):
		return any(_expr_invokes_lookup(v) for v in expr)
	# Bare string / number / bool / None — never an op invocation.
	return False


def _check_lookup_permission(wd: WorkflowDef, report: ValidationReport) -> None:
	"""A transition that calls a ``lookup`` op (or ``http_call`` to a
	``/lookup`` URL) must be paired with a permission gate.

	E-39 / C-10: the guard expression walker is AST-aware (see
	:func:`_expr_invokes_lookup`) so a literal string ``"lookup_failed"``
	does not trigger a false positive.
	"""

	for t in wd.transitions:
		uses_lookup = any(_expr_invokes_lookup(g.expr) for g in t.guards)
		if not uses_lookup:
			for e in t.effects:
				if e.kind == "http_call" and (e.url or "").startswith("/lookup"):
					uses_lookup = True
					break
				if e.expr is not None and _expr_invokes_lookup(e.expr):
					uses_lookup = True
					break
		has_perm_gate = any(g.kind == "permission" for g in t.gates)
		if uses_lookup and not has_perm_gate:
			report.warnings.append(
				f"transition {t.id!r} touches a lookup but has no permission gate"
			)


def validate(data: dict[str, Any] | WorkflowDef, *, strict: bool = False) -> ValidationReport:
	"""Validate *data* (raw dict or already-parsed WorkflowDef) and return a report."""

	report = ValidationReport()

	# Schema check on raw dict (preserves all original violations)
	if isinstance(data, WorkflowDef):
		raw = data.model_dump(mode="json")
		wd = data
	else:
		raw = data
		_check_schema(raw, report)
		if report.errors:
			# Avoid raising on parse errors — caller wants the report.
			if strict:
				raise ValidationError(report.errors[0])
			return report
		try:
			wd = WorkflowDef.model_validate(raw)
		except Exception as exc:
			report.errors.append(f"pydantic: {exc}")
			if strict:
				raise ValidationError(report.errors[-1]) from exc
			return report

	if not raw or not report.ok:
		# raw was provided + earlier checks failed; skip downstream
		pass

	_check_state_topology(wd, report)
	_check_priorities(wd, report)
	_check_subworkflow_cycle(wd, report)
	_check_expr_arity(wd, report)
	_check_lookup_permission(wd, report)

	if strict and report.errors:
		raise ValidationError(report.errors[0])
	return report
