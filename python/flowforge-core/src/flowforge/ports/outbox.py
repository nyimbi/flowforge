"""OutboxRegistry port — handler dispatch with multi-backend support."""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol, runtime_checkable

from .types import OutboxEnvelope

OutboxHandler = Callable[[OutboxEnvelope], Awaitable[None]]


@runtime_checkable
class OutboxRegistry(Protocol):
	"""Registry of outbox handlers.

	Per portability spec A-1, multi-backend hosts (e.g., dramatiq +
	temporal) register handlers under named backends. The engine only
	enqueues; backends drain and dispatch.
	"""

	def register(
		self,
		kind: str,
		handler: OutboxHandler,
		backend: str = "default",
	) -> None:
		"""Register *handler* for *kind* under *backend*."""

	async def dispatch(self, envelope: OutboxEnvelope, backend: str = "default") -> None:
		"""Dispatch *envelope* to the matching handler. Raises if unregistered."""

	def list_kinds(self, backend: str = "default") -> list[str]:
		"""List registered kinds — used by validators + drift checks."""
