"""TaskTrackerPort — surface stuck workflows to ops dashboards."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TaskTrackerPort(Protocol):
	"""Operational task creation hook.

	Optional: engine still emits diagnosis JSON when this is the noop
	impl; hosts that wire a real tracker also get rows in their
	operator queue.
	"""

	async def create_task(self, kind: str, ref: str, note: str) -> str:
		"""Create an operational task; return its id."""
