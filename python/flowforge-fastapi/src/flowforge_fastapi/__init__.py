"""flowforge-fastapi — FastAPI HTTP/WS adapters.

Public surface:

* :func:`mount_routers` — attach designer + runtime + WS routers to an
  existing :class:`fastapi.FastAPI` app.
* :class:`WorkflowDefRegistry` — in-memory definition lookup; the
  routers consult this to resolve ``def_key`` lookups.
* :class:`InstanceStore` — engine snapshot store wrapping
  :class:`flowforge.engine.InMemorySnapshotStore` plus an instance/def
  index so the runtime router can ``GET /instances/{id}`` without
  re-deriving the def.
* :class:`WorkflowEventsHub` — pub/sub used by the WS endpoint.
* Auth helpers: :class:`PrincipalExtractor`,
  :class:`StaticPrincipalExtractor`, :class:`CookiePrincipalExtractor`,
  :func:`csrf_protect`.

The adapter does not own state — every port goes through
:mod:`flowforge.config`. Tests in this package run with
:func:`flowforge.config.reset_to_fakes` and ``httpx.ASGITransport``.
"""

from __future__ import annotations

from typing import Sequence

from .auth import (
	ConfigError,
	CookiePrincipalExtractor,
	PrincipalExtractor,
	StaticPrincipalExtractor,
	WSPrincipalExtractor,
	csrf_cookie_name,
	csrf_header_name,
	csrf_protect,
	issue_csrf_token,
)
from .registry import (
	InstanceStore,
	WorkflowDefRegistry,
	get_instance_store,
	get_registry,
	reset_state,
)
from .router_designer import build_designer_router
from .router_runtime import build_runtime_router
from .ws import WorkflowEventsHub, build_ws_router, get_events_hub

__version__ = "0.1.0"


def mount_routers(
	app,
	*,
	prefix: str = "",
	principal_extractor: "PrincipalExtractor | None" = None,
	tags: Sequence[str] | None = None,
	require_csrf: bool = False,
) -> None:
	"""Attach designer + runtime + WS routers to *app*.

	Parameters mirror FastAPI conventions:

	* ``prefix`` — common path prefix; designer mounts under
	  ``{prefix}`` and runtime under ``{prefix}``; WS mounts at
	  ``{prefix}/ws``.
	* ``principal_extractor`` — pluggable identity. Defaults to a
	  :class:`StaticPrincipalExtractor` returning a "system" principal so
	  unit tests work out of the box.
	* ``require_csrf`` — when True, mutating runtime endpoints require a
	  matching CSRF token (cookie + ``X-CSRF-Token`` header).
	"""

	from fastapi import FastAPI

	if not isinstance(app, FastAPI):  # pragma: no cover - defensive only
		raise TypeError(f"mount_routers expects FastAPI; got {type(app).__name__}")

	designer = build_designer_router(
		principal_extractor=principal_extractor,
		tags=tags,
	)
	runtime = build_runtime_router(
		principal_extractor=principal_extractor,
		tags=tags,
		require_csrf=require_csrf,
	)
	ws = build_ws_router(principal_extractor=principal_extractor)

	# E-41 / FA-04: hub is request-scoped at the app level.  Each
	# ``mount_routers`` call attaches a fresh :class:`WorkflowEventsHub`
	# to ``app.state`` and overrides the ``get_events_hub`` dependency
	# so two FastAPI apps in the same process never share subscribers.
	# Cross-test leak is structurally impossible.
	app_hub = WorkflowEventsHub()
	app.state.flowforge_events_hub = app_hub
	app.dependency_overrides[get_events_hub] = lambda: app_hub

	app.include_router(designer, prefix=prefix)
	app.include_router(runtime, prefix=prefix)
	app.include_router(ws, prefix=prefix)


__all__ = [
	"ConfigError",
	"CookiePrincipalExtractor",
	"InstanceStore",
	"PrincipalExtractor",
	"StaticPrincipalExtractor",
	"WSPrincipalExtractor",
	"WorkflowDefRegistry",
	"WorkflowEventsHub",
	"__version__",
	"build_designer_router",
	"build_runtime_router",
	"build_ws_router",
	"csrf_cookie_name",
	"csrf_header_name",
	"csrf_protect",
	"get_events_hub",
	"get_instance_store",
	"get_registry",
	"issue_csrf_token",
	"mount_routers",
	"reset_state",
]
