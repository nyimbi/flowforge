"""Designer-side HTTP router.

Endpoints:

* ``GET /defs`` — list registered workflow definitions.
* ``GET /defs/{key}`` — fetch one (optionally pinned to a version).
* ``POST /defs/validate`` — run :func:`flowforge.compiler.validate` on a
  posted definition; returns the structured report.
* ``GET /catalog`` — :func:`flowforge.compiler.build_catalog` over all
  registered defs.

These endpoints are READ-only with respect to the engine; they exist so
a designer UI can introspect the registry without poking the runtime
side. Authentication still applies — designers are authenticated users.
"""

from __future__ import annotations

from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from flowforge.compiler import build_catalog, validate as validate_def
from flowforge.dsl import WorkflowDef
from flowforge.ports.types import Principal

from .auth import PrincipalExtractor, StaticPrincipalExtractor
from .registry import WorkflowDefRegistry, get_registry


class ValidateRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	definition: dict[str, Any]
	strict: bool = False


class ValidateResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ok: bool
	errors: list[str]
	warnings: list[str]


def build_designer_router(
	*,
	principal_extractor: PrincipalExtractor | None = None,
	tags: Sequence[str] | None = None,
) -> APIRouter:
	"""Construct the designer router.

	The returned router carries no prefix; callers compose under
	whatever path they like (e.g. ``/api/v1/workflows``).
	"""

	extractor: PrincipalExtractor = principal_extractor or StaticPrincipalExtractor()
	router_tags: list[str | Any] = list(tags) if tags else ["flowforge-designer"]
	router = APIRouter(tags=router_tags)

	async def _principal(req_principal: Principal = Depends(extractor)) -> Principal:
		return req_principal

	@router.get("/defs")
	async def list_defs(
		registry: WorkflowDefRegistry = Depends(get_registry),
		_: Principal = Depends(_principal),
	) -> dict[str, Any]:
		return {"defs": registry.list()}

	@router.get("/defs/{key}")
	async def get_def(
		key: str,
		version: str | None = None,
		registry: WorkflowDefRegistry = Depends(get_registry),
		_: Principal = Depends(_principal),
	) -> dict[str, Any]:
		try:
			wd = registry.get(key, version)
		except KeyError as exc:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=str(exc),
			) from exc
		return wd.model_dump(mode="json")

	@router.post("/defs/validate", response_model=ValidateResponse)
	async def validate_endpoint(
		body: ValidateRequest,
		_: Principal = Depends(_principal),
	) -> ValidateResponse:
		# Run schema + topology checks. Catch the ``strict`` raise so we
		# always return a structured report.
		try:
			report = validate_def(body.definition, strict=body.strict)
		except Exception as exc:
			return ValidateResponse(ok=False, errors=[str(exc)], warnings=[])
		return ValidateResponse(
			ok=report.ok,
			errors=list(report.errors),
			warnings=list(report.warnings),
		)

	@router.get("/catalog")
	async def catalog(
		registry: WorkflowDefRegistry = Depends(get_registry),
		_: Principal = Depends(_principal),
	) -> dict[str, Any]:
		# Pull every (latest-version) def out of the registry and project.
		seen: dict[str, WorkflowDef] = {}
		for row in registry.list():
			key = row["key"]
			if key not in seen:
				seen[key] = registry.get(key)
		return build_catalog(list(seen.values()))

	return router


__all__ = ["ValidateRequest", "ValidateResponse", "build_designer_router"]
