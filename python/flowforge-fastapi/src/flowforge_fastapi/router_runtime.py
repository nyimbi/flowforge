"""Runtime HTTP router.

Endpoints:

* ``POST /instances`` — create a new instance from ``def_key`` (+ optional
  ``def_version`` and ``initial_context``). Returns the persisted
  snapshot.
* ``POST /instances/{id}/events`` — fire ``event`` (with optional
  ``payload``) against the instance. Returns the new snapshot + a
  summary of audit + outbox effects emitted.
* ``GET /instances/{id}`` — read the current snapshot.

Mutation endpoints honour CSRF when ``require_csrf=True`` is passed to
the builder.
"""

from __future__ import annotations

from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from flowforge.engine import Instance, fire as engine_fire, new_instance
from flowforge.ports.types import Principal

from .auth import PrincipalExtractor, StaticPrincipalExtractor, csrf_protect
from .registry import (
	InstanceStore,
	WorkflowDefRegistry,
	get_instance_store,
	get_registry,
)
from .ws import WorkflowEventsHub, get_events_hub


class CreateInstanceRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	def_key: str
	def_version: str | None = None
	initial_context: dict[str, Any] | None = None
	tenant_id: str = "default"
	instance_id: str | None = None


class FireEventRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	event: str
	payload: dict[str, Any] | None = None
	tenant_id: str = "default"


class InstanceView(BaseModel):
	model_config = ConfigDict(extra="forbid")

	id: str
	def_key: str
	def_version: str
	state: str
	context: dict[str, Any]
	history: list[str]
	saga: list[dict[str, Any]]
	created_entities: list[tuple[str, dict[str, Any]]]


class FireResultView(BaseModel):
	model_config = ConfigDict(extra="forbid")

	instance: InstanceView
	matched_transition_id: str | None
	new_state: str
	terminal: bool
	audit_event_kinds: list[str]
	outbox_kinds: list[str]


def _to_view(instance: Instance) -> InstanceView:
	return InstanceView(
		id=instance.id,
		def_key=instance.def_key,
		def_version=instance.def_version,
		state=instance.state,
		context=dict(instance.context),
		history=list(instance.history),
		saga=list(instance.saga),
		created_entities=list(instance.created_entities),
	)


def build_runtime_router(
	*,
	principal_extractor: PrincipalExtractor | None = None,
	tags: Sequence[str] | None = None,
	require_csrf: bool = False,
) -> APIRouter:
	"""Construct the runtime router.

	When ``require_csrf=True``, mutation endpoints add the
	:func:`flowforge_fastapi.auth.csrf_protect` dependency so the host
	can reuse one CSRF model across designer + runtime.
	"""

	extractor: PrincipalExtractor = principal_extractor or StaticPrincipalExtractor()
	router_tags: list[str | Any] = list(tags) if tags else ["flowforge-runtime"]
	router = APIRouter(tags=router_tags)

	async def _principal(req_principal: Principal = Depends(extractor)) -> Principal:
		return req_principal

	mutation_deps: list[Any] = []
	if require_csrf:
		mutation_deps.append(Depends(csrf_protect))

	@router.post(
		"/instances",
		response_model=InstanceView,
		status_code=status.HTTP_201_CREATED,
		dependencies=mutation_deps,
	)
	async def create_instance(
		body: CreateInstanceRequest,
		registry: WorkflowDefRegistry = Depends(get_registry),
		store: InstanceStore = Depends(get_instance_store),
		hub: WorkflowEventsHub = Depends(get_events_hub),
		principal: Principal = Depends(_principal),
	) -> InstanceView:
		try:
			wd = registry.get(body.def_key, body.def_version)
		except KeyError as exc:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=str(exc),
			) from exc
		instance = new_instance(
			wd,
			instance_id=body.instance_id,
			initial_context=body.initial_context,
		)
		await store.put(instance)
		await hub.publish(
			{
				"type": "instance.created",
				"instance_id": instance.id,
				"def_key": instance.def_key,
				"def_version": instance.def_version,
				"state": instance.state,
				"actor_user_id": principal.user_id,
				"tenant_id": body.tenant_id,
			}
		)
		return _to_view(instance)

	@router.post(
		"/instances/{instance_id}/events",
		response_model=FireResultView,
		dependencies=mutation_deps,
	)
	async def fire_event(
		instance_id: str,
		body: FireEventRequest,
		registry: WorkflowDefRegistry = Depends(get_registry),
		store: InstanceStore = Depends(get_instance_store),
		hub: WorkflowEventsHub = Depends(get_events_hub),
		principal: Principal = Depends(_principal),
	) -> FireResultView:
		instance = await store.get(instance_id)
		if instance is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"unknown instance: {instance_id}",
			)
		try:
			wd = registry.get(instance.def_key, instance.def_version)
		except KeyError as exc:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail=f"definition no longer registered: {exc}",
			) from exc

		prev_state = instance.state
		result = await engine_fire(
			wd,
			instance,
			body.event,
			payload=body.payload,
			principal=principal,
			tenant_id=body.tenant_id,
		)
		await store.put(instance)

		if result.matched_transition_id is not None and result.new_state != prev_state:
			await hub.publish(
				{
					"type": "instance.state_changed",
					"instance_id": instance.id,
					"def_key": instance.def_key,
					"from_state": prev_state,
					"to_state": result.new_state,
					"event": body.event,
					"transition_id": result.matched_transition_id,
					"terminal": result.terminal,
					"actor_user_id": principal.user_id,
					"tenant_id": body.tenant_id,
				}
			)

		return FireResultView(
			instance=_to_view(instance),
			matched_transition_id=result.matched_transition_id,
			new_state=result.new_state,
			terminal=result.terminal,
			audit_event_kinds=[e.kind for e in result.audit_events],
			outbox_kinds=[e.kind for e in result.outbox_envelopes],
		)

	@router.get("/instances/{instance_id}", response_model=InstanceView)
	async def read_instance(
		instance_id: str,
		store: InstanceStore = Depends(get_instance_store),
		_: Principal = Depends(_principal),
	) -> InstanceView:
		instance = await store.get(instance_id)
		if instance is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"unknown instance: {instance_id}",
			)
		return _to_view(instance)

	return router


__all__ = [
	"CreateInstanceRequest",
	"FireEventRequest",
	"FireResultView",
	"InstanceView",
	"build_runtime_router",
]
