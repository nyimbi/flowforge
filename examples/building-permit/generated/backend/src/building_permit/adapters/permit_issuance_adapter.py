"""Workflow adapter for Issue the Building Permit Certificate.

Wraps :func:`flowforge.engine.fire.fire` for the ``permit_issuance`` workflow.
The host service constructs an instance, then calls :func:`fire_event`
with each user/system event.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from flowforge import config as _flowforge_config
from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import FireResult, fire as _fire, new_instance
from flowforge.ports.metrics import FIRE_DURATION_HISTOGRAM
from flowforge.ports.types import Principal


WORKFLOW_KEY = "permit_issuance"
_DEF_PATH = Path(__file__).resolve().parents[3] / "workflows" / WORKFLOW_KEY / "definition.json"


# v0.3.0 W2 / item 12 — OpenTelemetry by construction. The OTel import
# is lazy so generated apps run without ``opentelemetry-api`` installed;
# in that case ``_otel_span`` returns a no-op context manager whose shape
# matches OTel's ``start_as_current_span`` so call-site code stays clean.
try:  # pragma: no cover - import-time fast path
	from opentelemetry import trace as _otel_trace
	_OTEL_TRACER: Any = _otel_trace.get_tracer("flowforge.permit_issuance")
except ImportError:  # pragma: no cover
	_OTEL_TRACER = None


@contextmanager
def _otel_span(name: str, attributes: dict[str, Any]) -> Iterator[Any]:
	"""Open an OTel span when ``opentelemetry`` is installed; else a no-op."""

	if _OTEL_TRACER is None:
		yield None
		return
	with _OTEL_TRACER.start_as_current_span(name, attributes=attributes) as span:
		yield span


def load_definition() -> WorkflowDef:
	"""Read + parse the JSON DSL definition once per import."""

	raw = json.loads(_DEF_PATH.read_text(encoding="utf-8"))
	return WorkflowDef.model_validate(raw)


_DEF: WorkflowDef | None = None


def _definition() -> WorkflowDef:
	global _DEF
	if _DEF is None:
		_DEF = load_definition()
	return _DEF


async def fire_event(
	event: str,
	*,
	payload: dict[str, Any] | None = None,
	principal: Principal,
	tenant_id: str = "default",
) -> FireResult:
	"""Fire one event against a fresh instance (testing default).

	Production callers replace this shim with a snapshot-store-backed
	instance lookup; the signature stays stable.
	"""

	wd = _definition()
	instance = new_instance(wd)
	span_attrs: dict[str, Any] = {
		"flowforge.tenant_id": tenant_id,
		"flowforge.jtbd_id": WORKFLOW_KEY,
		"flowforge.state": instance.state,
		"flowforge.event": event,
		"flowforge.principal_user_id": principal.user_id,
	}
	started = time.perf_counter()
	with _otel_span("flowforge.fire", span_attrs) as _span:
		result = await _fire(
			wd,
			instance,
			event,
			payload=payload or {},
			principal=principal,
			tenant_id=tenant_id,
		)
		if _span is not None:
			_span.set_attribute("flowforge.new_state", result.new_state)
	duration_seconds = time.perf_counter() - started
	metrics = getattr(_flowforge_config, "metrics", None)
	if metrics is not None:
		labels = {
			"tenant_id": tenant_id,
			"def_key": WORKFLOW_KEY,
			"state": result.new_state,
			"jtbd_id": WORKFLOW_KEY,
			"jtbd_version": "",
		}
		record_histogram = getattr(metrics, "record_histogram", None)
		if record_histogram is not None:
			record_histogram(FIRE_DURATION_HISTOGRAM, duration_seconds, labels)
		else:
			metrics.emit(FIRE_DURATION_HISTOGRAM, duration_seconds, labels)
	return result
