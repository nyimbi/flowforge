"""Saga ledger.

Saga steps are recorded onto :class:`flowforge.engine.fire.Instance.saga`
as effects fire. The compensation worker is a host concern; this module
provides the ledger model + helpers for replay determinism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SagaStep:
	kind: str
	args: dict[str, Any] = field(default_factory=dict)
	status: str = "pending"  # pending | done | compensated | failed


class SagaLedger:
	"""In-memory ledger keyed by instance id."""

	def __init__(self) -> None:
		self._rows: dict[str, list[SagaStep]] = {}

	def append(self, instance_id: str, step: SagaStep) -> None:
		self._rows.setdefault(instance_id, []).append(step)

	def list(self, instance_id: str) -> list[SagaStep]:
		return list(self._rows.get(instance_id, ()))

	def mark(self, instance_id: str, idx: int, status: str) -> None:
		rows = self._rows.get(instance_id) or []
		if 0 <= idx < len(rows):
			rows[idx] = SagaStep(kind=rows[idx].kind, args=rows[idx].args, status=status)
