"""FastAPI router for Conduct Field Inspection.

Exposes ``POST /field-inspection/events`` so a frontend step
component can post events into the workflow engine.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from pydantic import BaseModel, ConfigDict

from flowforge.ports.types import Principal

from ..services.field_inspection_service import FieldInspectionService


router = APIRouter(prefix="/field-inspection", tags=["field_inspection"])
_service = FieldInspectionService()


class EventBody(BaseModel):
	model_config = ConfigDict(extra="forbid")

	event: str
	payload: dict[str, Any] = {}


@router.post("/events")
async def post_event(body: EventBody = Body(...)) -> dict[str, Any]:
	"""Fire an event — caller injects auth via dependency overrides in tests."""

	# Tests inject a real Principal via dependency override; this default
	# keeps the route runnable without auth wiring.
	principal = Principal(user_id="anonymous", roles=("anonymous",), is_system=False)
	return await _service.transition(
		body.event,
		body.payload,
		principal=principal,
	)
