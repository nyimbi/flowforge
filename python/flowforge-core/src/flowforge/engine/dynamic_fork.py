"""Dynamic workflow branching — parallel_map state kind.

When an instance enters a ``parallel_map`` state the engine fans out
over a list of items stored in the instance context.  Each item is
processed as an independent ``ForkBranch``; when all branches report
completion the parent instance advances through the join transition.

This module provides the data structures and helper functions.  The
actual engine wiring happens in ``fire.py`` which calls
:func:`begin_fork` on entry to a ``parallel_map`` state and
:func:`collect_branch_result` / :func:`is_fork_complete` when a
branch fires its completion event back.

Design
------
Branches are lightweight records stored in ``instance.context``
under the reserved key ``"__fork__"``::

    {
        "__fork__": {
            "fork_id": "uuid7",
            "items": [...],
            "branches": {
                "0": {"item": ..., "status": "pending|complete|failed", "result": ...},
                ...
            },
            "policy": "all_complete|any_complete|ignore_failures"
        }
    }

No sub-instances are created — branches execute in the same
``Instance`` context using index-scoped context keys
(``context["__fork__"]["branches"]["0"]["result"]``).

Usage::

    from flowforge.engine.dynamic_fork import begin_fork, collect_branch_result, is_fork_complete

    # On entering parallel_map state:
    fork_state = begin_fork(instance, state_def, items=[...])

    # When a branch completion event arrives:
    collect_branch_result(instance, branch_index=0, result={"approved": True})

    # Check if ready to advance:
    if is_fork_complete(instance):
        # fire the join event
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import reduce
from typing import Any

from ..dsl.workflow_def import State

_log = logging.getLogger(__name__)

_FORK_KEY = "__fork__"


class DynamicForkError(RuntimeError):
	"""Raised when fork state is invalid or inconsistent."""


@dataclass
class BranchStatus:
	index: int
	item: Any
	status: str = "pending"  # pending | complete | failed
	result: Any = None
	error: str | None = None


@dataclass
class ForkState:
	fork_id: str
	items: list[Any]
	policy: str  # all_complete | any_complete | ignore_failures
	branches: list[BranchStatus] = field(default_factory=list)

	@classmethod
	def from_context(cls, context: dict[str, Any]) -> "ForkState | None":
		raw = context.get(_FORK_KEY)
		if raw is None:
			return None
		branches = [
			BranchStatus(
				index=int(k),
				item=v["item"],
				status=v.get("status", "pending"),
				result=v.get("result"),
				error=v.get("error"),
			)
			for k, v in sorted(raw["branches"].items(), key=lambda x: int(x[0]))
		]
		return cls(
			fork_id=raw["fork_id"],
			items=raw["items"],
			policy=raw.get("policy", "all_complete"),
			branches=branches,
		)

	def to_dict(self) -> dict[str, Any]:
		return {
			"fork_id": self.fork_id,
			"items": self.items,
			"policy": self.policy,
			"branches": {
				str(b.index): {
					"item": b.item,
					"status": b.status,
					"result": b.result,
					"error": b.error,
				}
				for b in self.branches
			},
		}


def _resolve_path(context: dict[str, Any], path: str) -> Any:
	"""Resolve dot-notation path from context."""
	parts = path.split(".")
	try:
		return reduce(lambda d, k: d[k] if isinstance(d, dict) else getattr(d, k, None), parts, context)
	except (KeyError, TypeError):
		return None


def begin_fork(
	context: dict[str, Any],
	state_def: State,
	*,
	fork_id: str,
	policy: str = "all_complete",
) -> ForkState:
	"""Initialise a dynamic fork for a ``parallel_map`` state.

	Reads ``state_def.fork_items_expr`` to locate the items list in
	*context*.  Writes the resulting :class:`ForkState` back into
	``context["__fork__"]`` and returns it.

	Args:
		context: The instance context (mutated in place).
		state_def: The ``parallel_map`` state definition.
		fork_id: Unique ID for this fork invocation.
		policy: ``"all_complete"`` (default) — advance only when every
		        branch is done.  ``"any_complete"`` — advance when the
		        first branch completes.  ``"ignore_failures"`` — treat
		        failed branches as complete.

	Raises:
		DynamicForkError: If ``fork_items_expr`` is not set or the
		                   resolved value is not a list.
	"""
	if not state_def.fork_items_expr:
		raise DynamicForkError(
			f"parallel_map state {state_def.name!r} has no fork_items_expr"
		)
	items = _resolve_path(context, state_def.fork_items_expr)
	if items is None:
		_log.warning(
			"begin_fork: fork_items_expr=%r resolved to None in context",
			state_def.fork_items_expr,
		)
		items = []
	if not isinstance(items, list):
		raise DynamicForkError(
			f"fork_items_expr={state_def.fork_items_expr!r} resolved to {type(items).__name__}, "
			"expected list"
		)

	fork = ForkState(
		fork_id=fork_id,
		items=list(items),
		policy=policy,
		branches=[BranchStatus(index=i, item=item) for i, item in enumerate(items)],
	)
	context[_FORK_KEY] = fork.to_dict()
	_log.info(
		"begin_fork: fork_id=%r state=%r items=%d policy=%r",
		fork_id, state_def.name, len(items), policy,
	)
	return fork


def collect_branch_result(
	context: dict[str, Any],
	branch_index: int,
	*,
	result: Any = None,
	error: str | None = None,
) -> ForkState:
	"""Record completion of one branch.

	Args:
		context: The instance context (mutated in place).
		branch_index: Zero-based index of the completed branch.
		result: The branch's output value (stored for join aggregation).
		error: If set, the branch is marked ``failed``; else ``complete``.

	Returns:
		Updated :class:`ForkState`.

	Raises:
		DynamicForkError: If no active fork exists or the index is out of range.
	"""
	fork = ForkState.from_context(context)
	if fork is None:
		raise DynamicForkError("collect_branch_result: no active fork in context")
	if branch_index < 0 or branch_index >= len(fork.branches):
		raise DynamicForkError(
			f"collect_branch_result: branch_index={branch_index} out of range "
			f"(fork has {len(fork.branches)} branches)"
		)
	branch = fork.branches[branch_index]
	branch.status = "failed" if error else "complete"
	branch.result = result
	branch.error = error
	context[_FORK_KEY] = fork.to_dict()
	return fork


def is_fork_complete(context: dict[str, Any]) -> bool:
	"""Return True if the active fork is ready to advance.

	Evaluates based on the fork's ``policy``:
	- ``all_complete``: every branch is ``complete`` or ``failed``
	- ``any_complete``: at least one branch is ``complete``
	- ``ignore_failures``: every branch is ``complete`` or ``failed`` (same as all_complete)
	"""
	fork = ForkState.from_context(context)
	if fork is None:
		return False
	if not fork.branches:
		return True

	policy = fork.policy
	if policy == "any_complete":
		return any(b.status == "complete" for b in fork.branches)
	# all_complete / ignore_failures
	return all(b.status in ("complete", "failed") for b in fork.branches)


def collect_fork_results(context: dict[str, Any]) -> list[Any]:
	"""Return a list of branch results from the active fork.

	Results are ordered by branch index.  Failed branches contribute
	``None`` (or their ``result`` if one was set before failure).
	"""
	fork = ForkState.from_context(context)
	if fork is None:
		return []
	return [b.result for b in fork.branches]


def clear_fork(context: dict[str, Any]) -> None:
	"""Remove the fork state from context after the join completes."""
	context.pop(_FORK_KEY, None)


__all__ = [
	"BranchStatus",
	"DynamicForkError",
	"ForkState",
	"begin_fork",
	"clear_fork",
	"collect_branch_result",
	"collect_fork_results",
	"is_fork_complete",
]
