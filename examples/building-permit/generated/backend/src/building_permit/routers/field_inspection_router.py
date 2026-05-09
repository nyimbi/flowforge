"""FastAPI router for Conduct Field Inspection.

Exposes ``POST /field-inspection/events`` so a frontend step
component can post events into the workflow engine. v0.3.0 W2 / item 6
adds router-level ``Idempotency-Key`` enforcement: missing header → 400,
in-flight duplicate → 409, replay within the TTL → cached 200.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from flowforge.ports.types import Principal

from ..field_inspection.idempotency import (
	IDEMPOTENCY_TTL_HOURS,
	check_idempotency_key,
	fingerprint_request,
	record_idempotency_response,
)
from ..services.field_inspection_service import FieldInspectionService


# v0.3.0 W2 / item 12 — OpenTelemetry by construction. Lazy import so
# the generated app runs without ``opentelemetry-api`` installed.
try:  # pragma: no cover - import-time fast path
	from opentelemetry import trace as _otel_trace
	_OTEL_TRACER: Any = _otel_trace.get_tracer("flowforge.field_inspection")
except ImportError:  # pragma: no cover
	_OTEL_TRACER = None


@contextmanager
def _otel_span(name: str, attributes: dict[str, Any]) -> Iterator[Any]:
	if _OTEL_TRACER is None:
		yield None
		return
	with _OTEL_TRACER.start_as_current_span(name, attributes=attributes) as span:
		yield span


router = APIRouter(prefix="/field-inspection", tags=["field_inspection"])
_service = FieldInspectionService()


class EventBody(BaseModel):
	model_config = ConfigDict(extra="forbid")

	event: str
	payload: dict[str, Any] = {}


@router.post("/events")
async def post_event(
	body: EventBody = Body(...),
	idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
	tenant_id: str = Header(default="default", alias="X-Tenant-Id"),
) -> dict[str, Any]:
	"""Fire an event — caller injects auth via dependency overrides in tests.

	v0.3.0 W2 / item 6: ``Idempotency-Key`` is required on every event
	POST. Replay within the configured TTL (``IDEMPOTENCY_TTL_HOURS``)
	returns the cached response; concurrent duplicates raise 409.
	"""

	if not idempotency_key:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Idempotency-Key header is required on POST /events",
		)

	span_attrs: dict[str, Any] = {
		"flowforge.tenant_id": tenant_id,
		"flowforge.jtbd_id": "field_inspection",
		"flowforge.event": body.event,
	}
	with _otel_span("flowforge.router.event", span_attrs) as _span:
		request_fingerprint = fingerprint_request(body.model_dump())
		hit = await check_idempotency_key(
			tenant_id=tenant_id,
			idempotency_key=idempotency_key,
			request_fingerprint=request_fingerprint,
		)
		if hit.kind == "in_flight":
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="Idempotency-Key is in flight on a concurrent request",
			)
		if hit.kind == "replay":
			assert hit.response_body is not None, "replay hit missing cached body"
			if _span is not None:
				_span.set_attribute("flowforge.idempotent_replay", True)
			return {**hit.response_body, "_idempotent_replay": True}

		# Tests inject a real Principal via dependency override; this default
		# keeps the route runnable without auth wiring.
		principal = Principal(user_id="anonymous", roles=("anonymous",), is_system=False)
		if _span is not None:
			_span.set_attribute("flowforge.principal_user_id", principal.user_id)
		result = await _service.transition(
			body.event,
			body.payload,
			principal=principal,
			tenant_id=tenant_id,
		)
		if _span is not None:
			_span.set_attribute("flowforge.new_state", result.get("state", ""))
		await record_idempotency_response(
			tenant_id=tenant_id,
			idempotency_key=idempotency_key,
			request_fingerprint=request_fingerprint,
			response_status=200,
			response_body=result,
		)
		return result
