"""WorkflowDiffer — structural diff between two workflow definition versions (E-13).

Compares two :class:`~flowforge.dsl.WorkflowDef` objects and returns a
:class:`WorkflowDiff` that annotates every added, removed, and changed state
and transition.  The diff is purely structural (data-level): it surfaces
*what* changed so the caller can decide *what it means*.

Usage::

    from flowforge.compiler.diff import diff_workflows, WorkflowDiff
    from flowforge.dsl import WorkflowDef

    old_wf = WorkflowDef.model_validate(old_data)
    new_wf = WorkflowDef.model_validate(new_data)
    diff = diff_workflows(old_wf, new_wf)

    print(diff.summary())
    if not diff.is_empty():
        # handle regressions, changelog generation, etc.
        ...

The module also accepts plain ``dict`` inputs via :func:`diff_workflow_dicts`
so callers don't need to construct Pydantic models first (e.g., from the CLI
or from the IDE debugger).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..dsl.workflow_def import WorkflowDef


# ---------------------------------------------------------------------------
# Diff result types
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class StateChange:
	"""A state present in both definitions whose attributes differ."""

	name: str
	# Maps field name → (old_value, new_value).
	changed_fields: dict[str, tuple[Any, Any]]


@dataclasses.dataclass(frozen=True)
class TransitionChange:
	"""A transition present in both definitions whose attributes differ."""

	id: str
	# Maps field name → (old_value, new_value).
	changed_fields: dict[str, tuple[Any, Any]]


@dataclasses.dataclass(frozen=True)
class WorkflowDiff:
	"""Structural diff between two workflow definition versions.

	All tuple fields use tuples (not lists) so the object is hashable and
	can be used as a dict key or stored in a frozenset without copying.
	"""

	old_key: str
	new_key: str
	old_version: str
	new_version: str

	# State-level changes
	added_states: tuple[str, ...]           # state names present in new but not old
	removed_states: tuple[str, ...]         # state names present in old but not new
	changed_states: tuple[StateChange, ...] # states present in both with field diffs

	# Transition-level changes
	added_transitions: tuple[str, ...]              # transition ids in new but not old
	removed_transitions: tuple[str, ...]            # transition ids in old but not new
	changed_transitions: tuple[TransitionChange, ...] # transitions in both with field diffs

	# Top-level header changes
	initial_state_changed: bool
	old_initial_state: str
	new_initial_state: str

	def is_empty(self) -> bool:
		"""Return ``True`` when no structural change is detected."""
		return not (
			self.added_states
			or self.removed_states
			or self.changed_states
			or self.added_transitions
			or self.removed_transitions
			or self.changed_transitions
			or self.initial_state_changed
		)

	def summary(self) -> str:
		"""Return a human-readable multi-line summary of the diff."""
		lines: list[str] = [
			f"diff  {self.old_key}@{self.old_version} → {self.new_key}@{self.new_version}"
		]

		if self.initial_state_changed:
			lines.append(
				f"  ~ initial_state  ({self.old_initial_state} → {self.new_initial_state})"
			)

		for name in self.added_states:
			lines.append(f"  + state  {name}")
		for name in self.removed_states:
			lines.append(f"  - state  {name}")
		for sc in self.changed_states:
			for field, (old, new) in sc.changed_fields.items():
				lines.append(f"  ~ state  {sc.name}.{field}  ({old!r} → {new!r})")

		for tid in self.added_transitions:
			lines.append(f"  + transition  {tid}")
		for tid in self.removed_transitions:
			lines.append(f"  - transition  {tid}")
		for tc in self.changed_transitions:
			for field, (old, new) in tc.changed_fields.items():
				lines.append(f"  ~ transition  {tc.id}.{field}  ({old!r} → {new!r})")

		if self.is_empty():
			lines.append("  (no structural changes)")

		return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _state_fields(state: Any) -> dict[str, Any]:
	"""Extract comparable fields from a State model."""
	return {
		"kind": state.kind,
		"swimlane": state.swimlane,
		"form_spec_id": state.form_spec_id,
		"sla": state.sla.model_dump() if state.sla else None,
		"subworkflow_key": state.subworkflow_key,
	}


def _transition_fields(tr: Any) -> dict[str, Any]:
	"""Extract comparable fields from a Transition model."""
	return {
		"event": tr.event,
		"from_state": tr.from_state,
		"to_state": tr.to_state,
		"priority": tr.priority,
		"guards": [g.model_dump() for g in tr.guards],
		"gates": [g.model_dump() for g in tr.gates],
		"effects": [e.model_dump() for e in tr.effects],
	}


def _changed_fields(
	old_fields: dict[str, Any],
	new_fields: dict[str, Any],
) -> dict[str, tuple[Any, Any]]:
	changed: dict[str, tuple[Any, Any]] = {}
	all_keys = set(old_fields) | set(new_fields)
	for key in sorted(all_keys):
		old_val = old_fields.get(key)
		new_val = new_fields.get(key)
		if old_val != new_val:
			changed[key] = (old_val, new_val)
	return changed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff_workflows(old: WorkflowDef, new: WorkflowDef) -> WorkflowDiff:
	"""Compute a structural diff between *old* and *new* workflow definitions.

	Both arguments must be :class:`~flowforge.dsl.WorkflowDef` instances.
	Use :func:`diff_workflow_dicts` to pass raw ``dict`` inputs.
	"""
	assert isinstance(old, WorkflowDef), "old must be a WorkflowDef"
	assert isinstance(new, WorkflowDef), "new must be a WorkflowDef"

	# States: keyed by name
	old_states = {s.name: s for s in old.states}
	new_states = {s.name: s for s in new.states}

	old_state_names = set(old_states)
	new_state_names = set(new_states)

	added_states = tuple(sorted(new_state_names - old_state_names))
	removed_states = tuple(sorted(old_state_names - new_state_names))
	changed_states: list[StateChange] = []
	for name in sorted(old_state_names & new_state_names):
		fields_diff = _changed_fields(
			_state_fields(old_states[name]),
			_state_fields(new_states[name]),
		)
		if fields_diff:
			changed_states.append(StateChange(name=name, changed_fields=fields_diff))

	# Transitions: keyed by id
	old_transitions = {t.id: t for t in old.transitions}
	new_transitions = {t.id: t for t in new.transitions}

	old_tr_ids = set(old_transitions)
	new_tr_ids = set(new_transitions)

	added_transitions = tuple(sorted(new_tr_ids - old_tr_ids))
	removed_transitions = tuple(sorted(old_tr_ids - new_tr_ids))
	changed_transitions: list[TransitionChange] = []
	for tid in sorted(old_tr_ids & new_tr_ids):
		fields_diff = _changed_fields(
			_transition_fields(old_transitions[tid]),
			_transition_fields(new_transitions[tid]),
		)
		if fields_diff:
			changed_transitions.append(
				TransitionChange(id=tid, changed_fields=fields_diff)
			)

	# Initial state
	initial_changed = old.initial_state != new.initial_state

	return WorkflowDiff(
		old_key=old.key,
		new_key=new.key,
		old_version=old.version,
		new_version=new.version,
		added_states=added_states,
		removed_states=removed_states,
		changed_states=tuple(changed_states),
		added_transitions=added_transitions,
		removed_transitions=removed_transitions,
		changed_transitions=tuple(changed_transitions),
		initial_state_changed=initial_changed,
		old_initial_state=old.initial_state,
		new_initial_state=new.initial_state,
	)


def diff_workflow_dicts(
	old: dict[str, Any],
	new: dict[str, Any],
) -> WorkflowDiff:
	"""Convenience wrapper: validate both dicts as :class:`WorkflowDef` and diff.

	Raises :exc:`pydantic.ValidationError` if either dict fails schema
	validation — the same error the compiler would raise on input.
	"""
	assert isinstance(old, dict), "old must be a dict"
	assert isinstance(new, dict), "new must be a dict"
	return diff_workflows(
		WorkflowDef.model_validate(old),
		WorkflowDef.model_validate(new),
	)


__all__ = [
	"StateChange",
	"TransitionChange",
	"WorkflowDiff",
	"diff_workflow_dicts",
	"diff_workflows",
]
