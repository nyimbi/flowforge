"""MetricsPort — minimal emit-only metrics surface."""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class MetricsPort(Protocol):
	"""Emit a numeric metric.

	Default labels per portability §B-10: ``{tenant_id, def_key, state}``.
	Hosts may wrap to relabel for Datadog / Prometheus / etc.
	"""

	def emit(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
		"""Emit metric *name* = *value* with optional labels."""
