"""OTel-backed implementation of :class:`flowforge.ports.tracing.TracingPort`.

Spans returned from :meth:`OtelTracing.start_span` satisfy the
:class:`flowforge.ports.tracing.Span` Protocol. The implementation is
async-context-manager-shaped so the call site reads identically with the
in-memory fake :class:`flowforge.testing.port_fakes.NoopTracing`.
"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import OpenTelemetryNotInstalled


class OtelSpan:
	"""Adapter span — delegates to an OTel ``Span`` instance."""

	def __init__(self, otel_span: Any) -> None:
		self._span = otel_span

	def set_attribute(self, key: str, value: Any) -> None:
		assert isinstance(key, str), "span attribute key must be a string"
		self._span.set_attribute(key, value)

	def record_exception(self, exc: BaseException) -> None:
		assert isinstance(exc, BaseException)
		self._span.record_exception(exc)
		# Mark the span as errored. OTel exposes the StatusCode enum on
		# ``opentelemetry.trace.status``; use its ERROR member if
		# available so consumers see a non-OK span.
		try:
			from opentelemetry.trace import Status, StatusCode
		except ImportError:  # pragma: no cover - SDK absent path tested separately
			return
		self._span.set_status(Status(StatusCode.ERROR, description=str(exc)))


class _OtelSpanCtx:
	"""Async context manager wrapping an OTel ``start_as_current_span``."""

	def __init__(self, tracer: Any, name: str, attributes: Mapping[str, Any] | None) -> None:
		self._tracer = tracer
		self._name = name
		self._attributes = dict(attributes or {})
		self._cm: Any = None
		self._span: OtelSpan | None = None

	async def __aenter__(self) -> OtelSpan:
		# OTel's ``start_as_current_span`` is a sync context manager; we
		# enter it eagerly inside the async __aenter__ so the span is
		# active for the entire ``async with`` body without bridging
		# threading contexts.
		self._cm = self._tracer.start_as_current_span(self._name, attributes=self._attributes)
		raw_span = self._cm.__enter__()
		self._span = OtelSpan(raw_span)
		return self._span

	async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
		assert self._cm is not None, "OTel span context not entered"
		# Mirror the no-op fake: record exception on the span before
		# exiting so the OTel exporter sees the error status.
		if exc is not None and isinstance(exc, BaseException) and self._span is not None:
			self._span.record_exception(exc)
		self._cm.__exit__(exc_type, exc, tb)


class OtelTracing:
	"""OpenTelemetry-backed :class:`flowforge.ports.tracing.TracingPort`.

	Construction acquires a tracer via the global OTel API; the host is
	expected to install a ``TracerProvider`` (typically with an OTLP /
	console / in-memory exporter) before the first ``start_span`` call.
	"""

	def __init__(self, tracer_name: str = "flowforge") -> None:
		assert isinstance(tracer_name, str) and tracer_name, \
			"tracer_name must be a non-empty string"
		try:
			from opentelemetry import trace as _otel_trace
		except ImportError as exc:  # pragma: no cover - covered in tests via a fake-import helper
			raise OpenTelemetryNotInstalled("opentelemetry") from exc
		self._tracer = _otel_trace.get_tracer(tracer_name)
		self._tracer_name = tracer_name

	def start_span(
		self,
		name: str,
		attributes: Mapping[str, Any] | None = None,
	) -> _OtelSpanCtx:
		assert isinstance(name, str) and name, "span name must be a non-empty string"
		return _OtelSpanCtx(self._tracer, name, attributes)
