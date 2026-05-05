"""Signal correlator.

Signals are external events that need to land on the right instance.
The correlator stores pending signals keyed by ``(signal_name, key)``
and returns matches when the engine asks.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Signal:
	name: str
	correlation_key: str
	payload: dict[str, Any]


class SignalCorrelator:
	def __init__(self) -> None:
		self._pending: dict[tuple[str, str], list[Signal]] = defaultdict(list)

	def push(self, sig: Signal) -> None:
		self._pending[(sig.name, sig.correlation_key)].append(sig)

	def consume(self, name: str, correlation_key: str) -> Signal | None:
		key = (name, correlation_key)
		bucket = self._pending.get(key)
		if not bucket:
			return None
		return bucket.pop(0)

	def pending_count(self) -> int:
		return sum(len(v) for v in self._pending.values())
