"""NotificationPort — multichannel template rendering + send."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .types import NotificationSpec


@runtime_checkable
class NotificationPort(Protocol):
	"""Notification fanout.

	Hosts register templates at startup; the engine emits notify
	envelopes via the OutboxRegistry, which the worker drains and
	hands to this port for actual delivery.
	"""

	async def render(
		self,
		template_id: str,
		locale: str,
		ctx: dict[str, Any],
	) -> tuple[str, str]:
		"""Render the (subject, body) pair for *template_id*."""
		...

	async def send(
		self,
		channel: str,
		recipient: str,
		rendered: tuple[str, str],
	) -> None:
		"""Deliver the rendered (subject, body) over *channel* to *recipient*."""

	async def register_template(self, spec: NotificationSpec) -> None:
		"""Idempotent template registration."""
