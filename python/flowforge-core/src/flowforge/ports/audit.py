"""AuditSink port — append-only event log with hash-chain integrity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .types import AuditEvent


@dataclass(frozen=True)
class Verdict:
	"""Outcome of a chain-verification call."""

	ok: bool
	first_bad_event_id: str | None = None
	checked_count: int = 0
	unsupported: bool = False

	@classmethod
	def supported_ok(cls, count: int) -> "Verdict":
		return cls(ok=True, checked_count=count)

	@classmethod
	def supported_bad(cls, bad_id: str, count: int) -> "Verdict":
		return cls(ok=False, first_bad_event_id=bad_id, checked_count=count)

	@classmethod
	def unsupported_(cls) -> "Verdict":
		return cls(ok=True, unsupported=True)


@runtime_checkable
class AuditSink(Protocol):
	"""Write + verify framework audit events.

	The engine calls :meth:`record` for every transition firing, every
	saga step, every elevation entry/exit. Implementations MUST persist
	atomically with the firing transaction so audit cannot drift from
	state. ``flowforge-audit-pg`` ships the default hash-chain impl.
	"""

	async def record(self, event: AuditEvent) -> str:
		"""Append *event*; return the assigned event id."""

	async def verify_chain(self, since: str | None = None) -> Verdict:
		"""Verify hash chain integrity from *since* (or beginning)."""

	async def redact(self, paths: list[str], reason: str) -> int:
		"""Tombstone the listed JSON paths across audit rows; return count.

		Hash chain MUST remain valid after redaction (use a tombstone
		marker, not deletion).
		"""
