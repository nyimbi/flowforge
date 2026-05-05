"""Replay reconstructor.

Given a workflow def and a chronological list of recorded events, replay
them through the simulator and return the final instance. Used by the
``flowforge replay`` CLI and parity tests.
"""

from __future__ import annotations

from typing import Any

from ..dsl import WorkflowDef
from ..engine.fire import Instance, fire, new_instance
from ..ports.types import Principal


async def reconstruct(
	wd: WorkflowDef,
	events: list[tuple[str, dict[str, Any]]],
	*,
	initial_context: dict[str, Any] | None = None,
	instance_id: str | None = None,
	tenant_id: str = "replay",
) -> Instance:
	"""Re-fire each event in order; return the resulting instance."""

	instance = new_instance(wd, instance_id=instance_id, initial_context=initial_context)
	principal = Principal(user_id="replay", is_system=True)
	for event_name, payload in events:
		fr = await fire(
			wd,
			instance,
			event_name,
			payload=payload,
			principal=principal,
			tenant_id=tenant_id,
		)
		if fr.terminal:
			break
	return instance
