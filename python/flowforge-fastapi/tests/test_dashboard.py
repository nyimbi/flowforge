"""Tests for the ops dashboard router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from flowforge_fastapi.dashboard import make_dashboard_router


# ---------------------------------------------------------------------------
# Router construction
# ---------------------------------------------------------------------------

def test_make_dashboard_router_returns_api_router():
	from fastapi import APIRouter
	session_factory = MagicMock()
	router = make_dashboard_router(session_factory)
	assert isinstance(router, APIRouter)


def test_dashboard_routes_registered():
    session_factory = MagicMock()
    router = make_dashboard_router(session_factory)
    paths = {route.path for route in router.routes}
    assert "/flowforge/dashboard/" in paths or any("/dashboard" in p for p in paths)
    assert "/flowforge/dashboard/health" in paths


def test_custom_prefix():
	session_factory = MagicMock()
	router = make_dashboard_router(session_factory, prefix="/ops/dashboard")
	paths = {route.path for route in router.routes}
	assert any("/ops/dashboard" in p for p in paths)


# ---------------------------------------------------------------------------
# HTTP responses via TestClient
# ---------------------------------------------------------------------------

def _app_with_mock_session(rows_by_query: dict | None = None) -> FastAPI:
	"""Build a FastAPI app with the dashboard router + a mock DB session."""
	from contextlib import asynccontextmanager

	mock_result = MagicMock()
	mock_result.fetchall.return_value = []
	mock_result.scalar.return_value = 0
	mock_result.keys.return_value = []

	mock_session = AsyncMock()
	mock_session.execute = AsyncMock(return_value=mock_result)

	@asynccontextmanager
	async def session_factory():
		yield mock_session

	app = FastAPI()
	router = make_dashboard_router(session_factory)
	app.include_router(router)
	return app


def test_dashboard_overview_returns_200():
	app = _app_with_mock_session()
	client = TestClient(app)
	resp = client.get("/flowforge/dashboard/")
	assert resp.status_code == 200


def test_dashboard_instances_returns_200():
	app = _app_with_mock_session()
	client = TestClient(app)
	resp = client.get("/flowforge/dashboard/instances")
	assert resp.status_code == 200


def test_dashboard_health_returns_json():
    app = _app_with_mock_session()
    client = TestClient(app)
    resp = client.get("/flowforge/dashboard/health")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert "status" in body
    assert "worker_pool" in body
    assert "outbox_backlog" in body


def test_dashboard_health_serves_html_when_requested():
    app = _app_with_mock_session()
    client = TestClient(app)
    resp = client.get(
        "/flowforge/dashboard/health",
        headers={"accept": "text/html"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Worker Pool Stats" in resp.text
    assert "Outbox queue depth" in resp.text


def test_dashboard_overview_html_contains_flowforge():
    app = _app_with_mock_session()
    client = TestClient(app)
    resp = client.get("/flowforge/dashboard/")
    assert resp.status_code == 200
	# Should return HTML with some indication of the dashboard
    content = resp.text
    assert "flowforge" in content.lower() or "FlowForge" in content or "Workflow" in content


def test_dashboard_overview_html_is_self_contained_and_refreshes():
    app = _app_with_mock_session()
    client = TestClient(app)
    resp = client.get("/flowforge/dashboard/")
    content = resp.text
    assert 'http-equiv="refresh" content="30"' in content
    assert "prefers-color-scheme" in content
    assert "--accent" in content
    assert "cdn.jsdelivr" not in content
    assert "unpkg.com" not in content
    for label in ("Overview", "Instances", "Tasks", "Audit", "Health"):
        assert label in content


def test_dashboard_instances_has_state_filter_and_pagination():
    app = _app_with_mock_session()
    client = TestClient(app)
    resp = client.get("/flowforge/dashboard/instances?state=active&page=2&limit=25")
    assert resp.status_code == 200
    assert 'name="state"' in resp.text
    assert "All states" in resp.text
    assert "Rows 0-0 of 0" in resp.text


def test_dashboard_tasks_returns_200():
	app = _app_with_mock_session()
	client = TestClient(app)
	resp = client.get("/flowforge/dashboard/tasks")
	assert resp.status_code == 200


def test_dashboard_audit_returns_200():
	app = _app_with_mock_session()
	client = TestClient(app)
	resp = client.get("/flowforge/dashboard/audit")
	assert resp.status_code == 200
