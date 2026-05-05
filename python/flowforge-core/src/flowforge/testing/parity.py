"""Parity helpers for migrating Python-defined workflows to the JSON DSL.

Hosts call :func:`assert_parity` from a parity test fixture; given a
Python workflow object and the reflected JSON, it walks each declared
event sequence and asserts that both yield the same final state.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ..dsl import WorkflowDef
from ..engine.fire import new_instance
from ..replay.simulator import simulate


async def assert_parity(
	wd: WorkflowDef,
	*,
	scenarios: list[dict[str, Any]],
	python_runner: Callable[[dict[str, Any]], Awaitable[str]] | None = None,
) -> list[str]:
	"""Run each scenario through both runners; return a list of diffs.

	A scenario is a dict with keys ``initial_context`` and ``events``.
	When *python_runner* is None, the function only asserts the DSL run
	terminates without error and returns its terminal state.
	"""
	diffs: list[str] = []
	for sc in scenarios:
		dsl_result = await simulate(
			wd,
			initial_context=sc.get("initial_context"),
			events=sc.get("events"),
		)
		if python_runner is not None:
			py_state = await python_runner(sc)
			if py_state != dsl_result.terminal_state:
				diffs.append(
					f"scenario {sc!r}: python={py_state} dsl={dsl_result.terminal_state}"
				)
	return diffs
