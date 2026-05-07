"""HTTP runtime router round-trip tests.

Drive the engine through ``POST /instances`` + ``POST /instances/{id}/events``
+ ``GET /instances/{id}`` using ``httpx.ASGITransport``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request, status

from flowforge_fastapi import (
	get_registry,
	mount_routers,
	reset_state,
)
from flowforge_fastapi.auth import (
	PrincipalExtractor,
	csrf_cookie_name,
	csrf_header_name,
	issue_csrf_token,
)
from flowforge.dsl import WorkflowDef
from flowforge.ports.types import Principal


pytestmark = pytest.mark.asyncio


PREFIX = "/api/v1/workflows"


async def test_create_then_fire_round_trip(client: httpx.AsyncClient) -> None:
	# 1. create
	create_resp = await client.post(
		f"{PREFIX}/instances",
		json={"def_key": "demo_claim", "tenant_id": "t-1"},
	)
	assert create_resp.status_code == 201, create_resp.text
	instance = create_resp.json()
	assert instance["state"] == "intake"
	assert instance["def_key"] == "demo_claim"
	instance_id = instance["id"]

	# 2. fire submit -> review
	fire_resp = await client.post(
		f"{PREFIX}/instances/{instance_id}/events",
		json={"event": "submit", "tenant_id": "t-1"},
	)
	assert fire_resp.status_code == 200, fire_resp.text
	body = fire_resp.json()
	assert body["new_state"] == "review"
	assert body["matched_transition_id"] == "submit"
	assert body["instance"]["context"]["submitted"] is True
	assert any(k.endswith(".transitioned") for k in body["audit_event_kinds"])

	# 3. read snapshot
	read_resp = await client.get(f"{PREFIX}/instances/{instance_id}")
	assert read_resp.status_code == 200
	snapshot = read_resp.json()
	assert snapshot["state"] == "review"
	assert snapshot["history"], "history should record the transition"

	# 4. fire approve -> terminal
	approve_resp = await client.post(
		f"{PREFIX}/instances/{instance_id}/events",
		json={"event": "approve"},
	)
	assert approve_resp.status_code == 200
	approve_body = approve_resp.json()
	assert approve_body["new_state"] == "approved"
	assert approve_body["terminal"] is True


async def test_create_unknown_def_returns_404(client: httpx.AsyncClient) -> None:
	resp = await client.post(
		f"{PREFIX}/instances",
		json={"def_key": "no_such_workflow"},
	)
	assert resp.status_code == 404


async def test_fire_unknown_instance_returns_404(client: httpx.AsyncClient) -> None:
	resp = await client.post(
		f"{PREFIX}/instances/does-not-exist/events",
		json={"event": "submit"},
	)
	assert resp.status_code == 404


async def test_get_unknown_instance_returns_404(client: httpx.AsyncClient) -> None:
	resp = await client.get(f"{PREFIX}/instances/does-not-exist")
	assert resp.status_code == 404


async def test_fire_unmatched_event_keeps_state(client: httpx.AsyncClient) -> None:
	create = await client.post(
		f"{PREFIX}/instances", json={"def_key": "demo_claim"}
	)
	instance_id = create.json()["id"]
	# 'approve' from intake doesn't match any transition (intake->review only).
	resp = await client.post(
		f"{PREFIX}/instances/{instance_id}/events",
		json={"event": "approve"},
	)
	assert resp.status_code == 200
	body = resp.json()
	assert body["matched_transition_id"] is None
	assert body["new_state"] == "intake"
	assert body["terminal"] is False


async def test_designer_endpoints_list_and_validate(
	client: httpx.AsyncClient,
	claim_workflow_def: WorkflowDef,
) -> None:
	resp = await client.get(f"{PREFIX}/defs")
	assert resp.status_code == 200
	rows = resp.json()["defs"]
	assert any(r["key"] == "demo_claim" for r in rows)

	get_one = await client.get(f"{PREFIX}/defs/demo_claim")
	assert get_one.status_code == 200
	assert get_one.json()["key"] == "demo_claim"

	# A bad definition (unreachable state) should produce a structured report.
	bad = claim_workflow_def.model_dump(mode="json", exclude_none=True)
	bad["states"].append({"name": "ghost", "kind": "manual_review"})
	validate = await client.post(
		f"{PREFIX}/defs/validate",
		json={"definition": bad},
	)
	assert validate.status_code == 200
	report = validate.json()
	assert report["ok"] is False
	assert any("ghost" in e for e in report["errors"])


async def test_designer_catalog_lists_subjects(client: httpx.AsyncClient) -> None:
	resp = await client.get(f"{PREFIX}/catalog")
	assert resp.status_code == 200
	catalog = resp.json()
	assert "claim" in catalog["subjects"]
	subj = catalog["subjects"]["claim"]
	assert "intake" in subj["states"]


async def test_principal_extractor_is_pluggable(
	claim_workflow_def: WorkflowDef,
) -> None:
	"""Plug in a custom extractor that reads X-User and rejects guests."""

	reset_state()
	from flowforge import config as ff_config

	ff_config.reset_to_fakes()
	get_registry().register(claim_workflow_def)

	class HeaderExtractor:
		async def __call__(self, request: Request) -> Principal:
			user = request.headers.get("X-User")
			if not user:
				raise HTTPException(
					status_code=status.HTTP_401_UNAUTHORIZED,
					detail="no X-User header",
				)
			return Principal(user_id=user, roles=("staff",))

	extractor: PrincipalExtractor = HeaderExtractor()
	app = FastAPI()
	mount_routers(app, prefix=PREFIX, principal_extractor=extractor)

	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as ac:
		# missing header -> 401
		anon = await ac.post(f"{PREFIX}/instances", json={"def_key": "demo_claim"})
		assert anon.status_code == 401

		# with header -> 201
		ok = await ac.post(
			f"{PREFIX}/instances",
			json={"def_key": "demo_claim"},
			headers={"X-User": "bob"},
		)
		assert ok.status_code == 201


async def test_csrf_protection_enforced_when_enabled(
	claim_workflow_def: WorkflowDef,
) -> None:
	"""When ``require_csrf=True`` mutations need cookie + header to match."""

	reset_state()
	from flowforge import config as ff_config

	ff_config.reset_to_fakes()
	get_registry().register(claim_workflow_def)

	app = FastAPI()
	# Tiny side endpoint that issues the CSRF cookie so we can read it.
	from fastapi.responses import JSONResponse

	@app.get("/_bootstrap")
	async def bootstrap() -> JSONResponse:
		response = JSONResponse({"token": ""})
		# E-41 / FA-02: dev_mode=True is required to opt out of the
		# Secure cookie default — the ASGI test transport uses plain
		# http://testserver which would otherwise drop the cookie.
		token = issue_csrf_token(response, secure=False, dev_mode=True)
		response.body = JSONResponse({"token": token}).body
		# JSONResponse caches Content-Length on render; recompute.
		response.headers["content-length"] = str(len(response.body))
		return response

	mount_routers(app, prefix=PREFIX, require_csrf=True)

	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as ac:
		# without CSRF -> 403
		denied = await ac.post(f"{PREFIX}/instances", json={"def_key": "demo_claim"})
		assert denied.status_code == 403

		# bootstrap to receive cookie
		boot = await ac.get("/_bootstrap")
		assert boot.status_code == 200
		token = boot.json()["token"]
		assert ac.cookies.get(csrf_cookie_name) == token

		# with matching header -> 201
		ok = await ac.post(
			f"{PREFIX}/instances",
			json={"def_key": "demo_claim"},
			headers={csrf_header_name: token},
		)
		assert ok.status_code == 201


async def test_state_change_publishes_to_hub(client: httpx.AsyncClient, app: FastAPI) -> None:
	"""A successful event publishes a state-change envelope to the hub.

	E-41 / FA-04: ``mount_routers`` now wires a per-app hub on
	``app.state.flowforge_events_hub`` and overrides the
	``get_events_hub`` dependency, so subscribers must use the
	app-scoped hub to receive published envelopes.
	"""

	hub = app.state.flowforge_events_hub
	queue = await hub.subscribe()

	create = await client.post(
		f"{PREFIX}/instances", json={"def_key": "demo_claim"}
	)
	instance_id = create.json()["id"]

	# Drain the create envelope first.
	first = await asyncio.wait_for(queue.get(), timeout=1.0)
	assert first["type"] == "instance.created"

	await client.post(
		f"{PREFIX}/instances/{instance_id}/events",
		json={"event": "submit"},
	)
	envelope: dict[str, Any] = await asyncio.wait_for(queue.get(), timeout=1.0)
	assert envelope["type"] == "instance.state_changed"
	assert envelope["from_state"] == "intake"
	assert envelope["to_state"] == "review"
	assert envelope["transition_id"] == "submit"

	await hub.unsubscribe(queue)


async def test_cookie_principal_extractor_round_trip() -> None:
	"""``CookiePrincipalExtractor`` issues + verifies a session cookie."""

	from flowforge_fastapi import CookiePrincipalExtractor

	extractor = CookiePrincipalExtractor(secret="s3cret")
	cookie_value = extractor.issue(
		Principal(user_id="carol", roles=("manager",), is_system=False)
	)

	# Reuse the request shape directly — no need for an app here.
	scope: dict[str, Any] = {
		"type": "http",
		"method": "GET",
		"headers": [
			(b"cookie", f"flowforge_session={cookie_value}".encode()),
		],
	}
	from starlette.requests import Request as StarletteRequest

	req = StarletteRequest(scope=scope)
	principal = await extractor(req)
	assert principal.user_id == "carol"
	assert "manager" in principal.roles

	# Tamper -> 401
	bad_scope = dict(scope)
	bad_scope["headers"] = [(b"cookie", b"flowforge_session=bogus.bogus")]
	bad_req = StarletteRequest(scope=bad_scope)
	with pytest.raises(HTTPException) as info:
		await extractor(bad_req)
	assert info.value.status_code == 401
