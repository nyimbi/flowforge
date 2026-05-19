"""FastAPI router for Submit a Building Permit Application.

Exposes ``POST /permit-intake/events`` so a frontend step
component can post events into the workflow engine. v0.3.0 W2 / item 6
adds router-level ``Idempotency-Key`` enforcement: missing header → 400,
in-flight duplicate → 409, replay within the TTL → cached 200.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from flowforge.ports.types import Principal

from ..permit_intake.idempotency import (
	IDEMPOTENCY_TTL_HOURS,
	check_idempotency_key,
	fingerprint_request,
	record_idempotency_response,
)
from ..services.permit_intake_service import PermitIntakeService


# v0.3.0 W2 / item 12 — OpenTelemetry by construction. Lazy import so
# the generated app runs without ``opentelemetry-api`` installed.
try:  # pragma: no cover - import-time fast path
	from opentelemetry import trace as _otel_trace
	_OTEL_TRACER: Any = _otel_trace.get_tracer("flowforge.permit_intake")
except ImportError:  # pragma: no cover
	_OTEL_TRACER = None


@contextmanager
def _otel_span(name: str, attributes: dict[str, Any]) -> Iterator[Any]:
	if _OTEL_TRACER is None:
		yield None
		return
	with _OTEL_TRACER.start_as_current_span(name, attributes=attributes) as span:
		yield span


router = APIRouter(prefix="/permit-intake", tags=["permit_intake"])
_service = PermitIntakeService()


class EventBody(BaseModel):
	model_config = ConfigDict(extra="forbid")

	event: str
	instance_id: str | None = None
	payload: dict[str, Any] = {}


async def require_principal() -> Principal:
	"""Host auth seam for generated routers.

	The generated scaffold is fail-closed: applications must override this
	dependency with their authenticated principal extractor before serving
	the router.
	"""

	raise HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="configure require_principal dependency before mounting generated router",
	)


@router.post("/events")
async def post_event(
	body: EventBody = Body(...),
	idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
	tenant_id: str = Header(..., alias="X-Tenant-Id"),
	principal: Principal = Depends(require_principal),
) -> dict[str, Any]:
	"""Fire an event using host-supplied auth and tenant context.

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
		"flowforge.jtbd_id": "permit_intake",
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

		if _span is not None:
			_span.set_attribute("flowforge.principal_user_id", principal.user_id)
		result = await _service.transition(
			body.event,
			body.payload,
			instance_id=body.instance_id,
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
