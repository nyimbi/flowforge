"""flowforge-otel — error types."""

from __future__ import annotations


class OpenTelemetryNotInstalled(RuntimeError):
	"""Raised when the OTel SDK is missing.

	The ``flowforge-otel`` package declares ``opentelemetry-api`` and
	``opentelemetry-sdk`` in its ``[otel]`` extra. Installing the
	package without that extra leaves the adapter classes importable
	(useful for type-stubbing) but they raise this error on
	construction.
	"""

	def __init__(self, missing_module: str = "opentelemetry") -> None:
		super().__init__(
			f"flowforge-otel requires the OpenTelemetry SDK. Install with "
			f"``pip install 'flowforge-otel[otel]'`` to pull in "
			f"{missing_module} ≥ 1.20."
		)
		self.missing_module = missing_module
