"""Tests for the ops dashboard router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
	body = resp.json()
	assert "status" in body


def test_dashboard_overview_html_contains_flowforge():
	app = _app_with_mock_session()
	client = TestClient(app)
	resp = client.get("/flowforge/dashboard/")
	assert resp.status_code == 200
	# Should return HTML with some indication of the dashboard
	content = resp.text
	assert "flowforge" in content.lower() or "FlowForge" in content or "Workflow" in content


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
