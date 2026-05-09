"""AnalyticsPort — closed-taxonomy product analytics emitter.

Item 16 of :doc:`docs/improvements`, W2 of
:doc:`docs/v0.3.0-engineering-plan`. Per Principle 4 (hexagonal port
discipline) the runtime side stays a port-only ABC: this module imports
no I/O dependency, no provider SDK, and no transport client. Hosts wire
Segment / Mixpanel / Amplitude / a noop sink themselves; the in-memory
fake under :mod:`flowforge.testing.port_fakes` ships with the framework
for tests and simulator runs.

The taxonomy itself is *closed* and is generated from each JTBD bundle:

* ``backend/src/<pkg>/analytics.py`` — Python ``StrEnum``.
* ``frontend/src/<pkg>/analytics.ts`` — TypeScript string-literal type.

Closure is enforced at build time by the ``analytics_taxonomy``
generator (per-bundle). This Protocol intentionally accepts an open
``str`` for *event_name* so existing tracker SDKs slot in without an
adapter shim — runtime callers should pass an enum member (Python) or
an ``AnalyticsEvent`` typed literal (TypeScript) so the closure
contract holds at the call site.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AnalyticsPort(Protocol):
	"""Emit a single product-analytics event.

	Implementations MUST be non-blocking on the request hot path —
	either fire-and-forget over an internal queue, or batch via the
	provider SDK's async client. The engine never awaits the result
	for routing decisions; analytics is observability, not control.

	*event_name* belongs to the closed taxonomy emitted by the
	``analytics_taxonomy`` generator for the host's bundle. *properties*
	is a JSON-serialisable mapping; PII-bearing keys MUST be filtered
	or hashed at the host adapter layer (this port does not enforce
	redaction — the audit ratchet covers PII surfaces separately).
	"""

	async def track(self, event_name: str, properties: dict[str, Any]) -> None:
		"""Record *event_name* with *properties*. MUST NOT raise on transport failure."""
		...
