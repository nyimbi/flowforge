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

import copy
from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from flowforge.dsl import WorkflowDef
from flowforge.engine import Instance, fire as engine_fire, new_instance
from flowforge.ports.types import Principal

from .auth import (
	PrincipalExtractor,
	TenantResolver,
	csrf_protect,
	resolve_principal_extractor,
	resolve_tenant_resolver,
)
from .registry import (
	InstanceStore,
	WorkflowDefRegistry,
	get_instance_store,
	get_registry,
)
from .ws import WorkflowEventsHub, get_events_hub


async def _fire_with_unit_of_work(
	*,
	wd: WorkflowDef,
	instance: Instance,
	event: str,
	payload: dict[str, Any] | None,
	principal: Principal,
	tenant_id: str,
	store: Any,
) -> Any:
	"""Run ``engine_fire`` + ``store.put`` as a single unit of work.

	E-41 / FA-05: pre-fix, ``engine_fire`` mutated *instance* in place and
	then a separate ``store.put`` ran independently.  If ``store.put``
	raised (DB down, optimistic-lock conflict, anything), the in-memory
	object had already advanced — a retry would start from the wrong
	state.  This helper deep-copies the pre-fire snapshot, runs both
	calls, and on a put failure rolls *instance* back so the caller's
	view matches reality.

	The deep-copy is the price of the rollback contract for an in-memory
	store; production hosts that wrap a real DB will swap this helper for
	a transactional ``async with store.transaction(): ...`` once the
	UoW protocol lands (audit-fix-plan §13.7).
	"""
	if (fire_and_commit := getattr(store, "fire_and_commit", None)) is not None:
		return await fire_and_commit(
			wd=wd,
			instance=instance,
			event=event,
			payload=payload,
			principal=principal,
			tenant_id=tenant_id,
		)

	pre_fire_snapshot = copy.deepcopy(instance)
	expected_seq = len(pre_fire_snapshot.history)
	result = await engine_fire(
		wd,
		instance,
		event,
		payload=payload,
		principal=principal,
		tenant_id=tenant_id,
	)
	try:
		if (compare_and_put := getattr(store, "compare_and_put", None)) is not None:
			await compare_and_put(instance, expected_seq=expected_seq)
		elif isinstance(store, InstanceStore):
			await store.put(instance, tenant_id=tenant_id)
		else:
			await store.put(instance)
	except Exception:
		# Restore in-memory instance fields from the snapshot so the
		# caller's reference no longer reflects an advanced state we
		# could not persist.  ``Instance`` is a dataclass-like object;
		# copying ``__dict__`` covers state, history, context, saga,
		# created_entities without naming each field.
		instance.__dict__.update(pre_fire_snapshot.__dict__)
		raise
	return result


class CreateInstanceRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	def_key: str
	def_version: str | None = None
	initial_context: dict[str, Any] | None = None
	tenant_id: str | None = None
	instance_id: str | None = None


class FireEventRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	event: str
	payload: dict[str, Any] | None = None
	tenant_id: str | None = None


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
	tenant_resolver: TenantResolver | None = None,
	tags: Sequence[str] | None = None,
	require_csrf: bool = False,
	allow_test_defaults: bool = False,
) -> APIRouter:
	"""Construct the runtime router.

	When ``require_csrf=True``, mutation endpoints add the
	:func:`flowforge_fastapi.auth.csrf_protect` dependency so the host
	can reuse one CSRF model across designer + runtime.
	"""

	extractor = resolve_principal_extractor(
		principal_extractor,
		allow_test_defaults=allow_test_defaults,
		surface="build_runtime_router",
	)
	resolved_tenant = resolve_tenant_resolver(
		tenant_resolver,
		allow_test_defaults=allow_test_defaults,
		surface="build_runtime_router",
	)
	router_tags: list[str | Any] = list(tags) if tags else ["flowforge-runtime"]
	router = APIRouter(tags=router_tags)

	async def _principal(req_principal: Principal = Depends(extractor)) -> Principal:
		return req_principal

	async def _tenant_id(
		request: Request,
		principal: Principal = Depends(_principal),
	) -> str:
		tenant_id = await resolved_tenant(request, principal)
		if not tenant_id:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="tenant resolution returned an empty tenant_id",
			)
		return tenant_id

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
		tenant_id: str = Depends(_tenant_id),
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
		await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)
		await hub.publish(
			{
				"type": "instance.created",
				"instance_id": instance.id,
				"def_key": instance.def_key,
				"def_version": instance.def_version,
				"state": instance.state,
				"actor_user_id": principal.user_id,
				"tenant_id": tenant_id,
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
		tenant_id: str = Depends(_tenant_id),
	) -> FireResultView:
		instance = await store.get_for_tenant(instance_id, tenant_id=tenant_id)
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
		# E-41 / FA-05: engine_fire + store.put as one unit of work.
		# A failure in store.put rolls instance back to its pre-fire snapshot.
		result = await _fire_with_unit_of_work(
			wd=wd,
			instance=instance,
			event=body.event,
			payload=body.payload,
			principal=principal,
			tenant_id=tenant_id,
			store=store,
		)

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
					"tenant_id": tenant_id,
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
		tenant_id: str = Depends(_tenant_id),
	) -> InstanceView:
		instance = await store.get_for_tenant(instance_id, tenant_id=tenant_id)
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
