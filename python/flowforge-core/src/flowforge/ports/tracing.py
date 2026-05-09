"""TracingPort — distributed-tracing surface for flowforge.

v0.3.0 W2 / item 12 (`docs/improvements.md`). Generated host code wraps
`fire`, effect-dispatch, and audit-append in spans whose attributes carry
`{tenant_id, jtbd_id, state, event, principal_user_id}` so a host with
OpenTelemetry installed sees a per-fire trace; without OTel installed
the generated code falls back to a no-op span (lazy import inside the
template — see `domain_service.py.j2`, `domain_router.py.j2`,
`workflow_adapter.py.j2`).

Hexagonal discipline: this module is **port-only**. No `opentelemetry`
import. The OTel-backed implementation lives in ``flowforge-otel``; the
in-memory test fake lives in ``flowforge.testing.port_fakes``.

Span-name conventions (host adapters MUST follow):

* ``flowforge.fire`` — engine-level fire; wraps the two-phase commit.
* ``flowforge.service.<event>`` — domain service entry point.
* ``flowforge.router.event`` — HTTP router entry point.
* ``flowforge.audit.append`` — audit-sink record() call.
* ``flowforge.outbox.dispatch`` — outbox dispatch call.

Standard attribute keys (host adapters MUST emit when known):

* ``flowforge.tenant_id``
* ``flowforge.jtbd_id``
* ``flowforge.state``
* ``flowforge.event``
* ``flowforge.principal_user_id``
"""

from __future__ import annotations

from typing import Any, AsyncContextManager, Mapping, Protocol, runtime_checkable


#: Canonical span attribute keys emitted by the engine + generated code.
#: Keep in lockstep with the OTel adapter and any host wrapper.
STANDARD_SPAN_ATTRIBUTES: tuple[str, ...] = (
	"flowforge.tenant_id",
	"flowforge.jtbd_id",
	"flowforge.state",
	"flowforge.event",
	"flowforge.principal_user_id",
)


#: Canonical span names emitted by generated host code. Tests assert on
#: this exact set so renaming a span is a SECURITY-NOTE-grade change.
STANDARD_SPAN_NAMES: tuple[str, ...] = (
	"flowforge.fire",
	"flowforge.router.event",
	"flowforge.service.submit",
	"flowforge.service.transition",
	"flowforge.audit.append",
	"flowforge.outbox.dispatch",
)


@runtime_checkable
class Span(Protocol):
	"""A single in-flight span. The context manager closes it."""

	def set_attribute(self, key: str, value: Any) -> None:
		"""Attach a key/value attribute to the span."""
		...

	def record_exception(self, exc: BaseException) -> None:
		"""Mark the span as errored and capture the exception details."""
		...


@runtime_checkable
class TracingPort(Protocol):
	"""Start spans for engine + generated code.

	Implementations return an async context manager so callers can
	``async with tracing.start_span(...) as span:`` regardless of whether
	the underlying tracer is OpenTelemetry, no-op, or a custom shim.

	Attributes are passed at start_span time (preferred — locks the
	attribute set in before any work) but ``Span.set_attribute`` exists
	for lazily-known values (e.g. ``new_state`` after a fire).
	"""

	def start_span(
		self,
		name: str,
		attributes: Mapping[str, Any] | None = None,
	) -> AsyncContextManager[Span]:
		"""Return an async context manager that yields a :class:`Span`.

		``name`` SHOULD be one of :data:`STANDARD_SPAN_NAMES`. Keys in
		``attributes`` SHOULD be one of :data:`STANDARD_SPAN_ATTRIBUTES`
		when their semantics match; hosts MAY add additional keys.
		"""
		...
