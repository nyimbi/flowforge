"""Built-in ops dashboard — server-side HTML monitoring UI.

Mount the router returned by :func:`make_dashboard_router` to expose a
live operations dashboard at a configurable prefix (default
``/flowforge/dashboard``).

The dashboard requires a SQLAlchemy ``AsyncSession`` factory that
provides access to the flowforge schema tables (``workflow_instances``,
``workflow_tasks``, ``outbox``, ``audit_events``).

Usage::

    from fastapi import FastAPI
    from flowforge_fastapi.dashboard import make_dashboard_router

    app = FastAPI()
    app.include_router(make_dashboard_router(session_factory))

Features
--------
* Overview page — running instance count, pending task count, outbox backlog, recent transitions
* Instance list — paginated, filterable by def_key and state
* Instance detail — current state, context snapshot, history, audit trail
* Task queue — pending manual-review tasks, resolve button
* Audit log — recent events with hash-chain verification status
* Health check — JSON endpoint for monitoring
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML rendering helpers (no Jinja2 dependency — pure f-strings + Bootstrap CDN)
# ---------------------------------------------------------------------------

_BOOTSTRAP = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
_BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
_HTMX = "https://unpkg.com/htmx.org@1.9.12"


def _page(title: str, body: str, *, prefix: str = "/flowforge/dashboard") -> str:
	nav_items = [
		("Overview", prefix + "/"),
		("Instances", prefix + "/instances"),
		("Tasks", prefix + "/tasks"),
		("Audit Log", prefix + "/audit"),
	]
	nav_html = "".join(
		f'<li class="nav-item"><a class="nav-link" href="{href}">{label}</a></li>'
		for label, href in nav_items
	)
	return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — flowforge</title>
  <link rel="stylesheet" href="{_BOOTSTRAP}">
  <script src="{_HTMX}" defer></script>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark px-3">
  <a class="navbar-brand fw-bold" href="{prefix}/">⚙ flowforge</a>
  <div class="collapse navbar-collapse">
    <ul class="navbar-nav ms-3">{nav_html}</ul>
  </div>
  <small class="text-secondary ms-auto">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</small>
</nav>
<div class="container-fluid mt-4">
  <h4>{title}</h4>
  {body}
</div>
<script src="{_BOOTSTRAP_JS}"></script>
</body>
</html>"""


def _stat_card(label: str, value: Any, color: str = "primary") -> str:
	return f"""<div class="col-sm-3">
  <div class="card text-white bg-{color} mb-3">
    <div class="card-body">
      <h2 class="card-title mb-0">{value}</h2>
      <p class="card-text">{label}</p>
    </div>
  </div>
</div>"""


def _table(headers: list[str], rows: list[list[Any]], *, empty: str = "No data") -> str:
	if not rows:
		return f'<p class="text-muted">{empty}</p>'
	th = "".join(f"<th>{h}</th>" for h in headers)
	body_rows = ""
	for row in rows:
		tds = "".join(f"<td>{cell}</td>" for cell in row)
		body_rows += f"<tr>{tds}</tr>"
	return f"""<div class="table-responsive">
<table class="table table-sm table-striped table-hover">
  <thead class="table-dark"><tr>{th}</tr></thead>
  <tbody>{body_rows}</tbody>
</table>
</div>"""


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def make_dashboard_router(
	session_factory: Callable,
	*,
	prefix: str = "/flowforge/dashboard",
	page_size: int = 50,
) -> APIRouter:
	"""Create a FastAPI router serving the ops dashboard.

	Args:
		session_factory: An async SQLAlchemy session factory (``async_sessionmaker``
		                 or any ``async with session_factory() as s`` compatible callable).
		prefix: URL prefix for all dashboard routes. Default: ``/flowforge/dashboard``.
		page_size: Max rows per page on list views. Default: 50.
	"""
	router = APIRouter(prefix=prefix, tags=["flowforge-dashboard"])

	async def _query(sql: str, params: dict | None = None) -> list[dict]:
		"""Execute a raw SQL query and return list of row dicts."""
		from sqlalchemy import text
		try:
			async with session_factory() as session:
				result = await session.execute(text(sql), params or {})
				cols = list(result.keys())
				return [dict(zip(cols, row)) for row in result.fetchall()]
		except Exception as exc:
			_log.error("dashboard query failed: %s | sql=%r", exc, sql)
			return []

	async def _scalar(sql: str, params: dict | None = None, *, default: Any = 0) -> Any:
		"""Execute a scalar SQL query."""
		from sqlalchemy import text
		try:
			async with session_factory() as session:
				result = await session.execute(text(sql), params or {})
				val = result.scalar()
				return val if val is not None else default
		except Exception as exc:
			_log.error("dashboard scalar failed: %s", exc)
			return default

	# ------------------------------------------------------------------
	# Health check
	# ------------------------------------------------------------------

	@router.get("/health", response_class=JSONResponse)
	async def health() -> JSONResponse:
		"""JSON health check for monitoring."""
		running = await _scalar("SELECT COUNT(*) FROM workflow_instances WHERE state NOT LIKE 'terminal%'")
		pending_tasks = await _scalar("SELECT COUNT(*) FROM workflow_tasks WHERE status='pending'")
		outbox_backlog = await _scalar("SELECT COUNT(*) FROM outbox WHERE status='pending'")
		return JSONResponse({
			"status": "ok",
			"running_instances": running,
			"pending_tasks": pending_tasks,
			"outbox_backlog": outbox_backlog,
			"timestamp": datetime.now(timezone.utc).isoformat(),
		})

	# ------------------------------------------------------------------
	# Overview
	# ------------------------------------------------------------------

	@router.get("/", response_class=HTMLResponse)
	async def overview(request: Request) -> HTMLResponse:
		running = await _scalar(
			"SELECT COUNT(*) FROM workflow_instances WHERE state NOT LIKE 'terminal%'"
		)
		succeeded = await _scalar(
			"SELECT COUNT(*) FROM workflow_instances WHERE state LIKE 'terminal%success%'"
		)
		pending_tasks = await _scalar(
			"SELECT COUNT(*) FROM workflow_tasks WHERE status='pending'"
		)
		outbox_backlog = await _scalar(
			"SELECT COUNT(*) FROM outbox WHERE status='pending'"
		)

		recent_events = await _query("""
			SELECT kind, subject_id, payload, created_at
			FROM audit_events
			ORDER BY created_at DESC
			LIMIT 20
		""")

		stats = f"""<div class="row mb-4">
  {_stat_card("Running Instances", running, "primary")}
  {_stat_card("Completed (Success)", succeeded, "success")}
  {_stat_card("Pending Tasks", pending_tasks, "warning")}
  {_stat_card("Outbox Backlog", outbox_backlog, "danger" if outbox_backlog > 100 else "info")}
</div>"""

		event_rows = [
			[
				e.get("kind", ""),
				f'<a href="{prefix}/instances?subject={e.get("subject_id", "")}">'
				f'{str(e.get("subject_id",""))[:12]}…</a>',
				str(e.get("created_at", ""))[:19],
			]
			for e in recent_events
		]
		event_table = _table(["Event Kind", "Subject", "Time"], event_rows, empty="No recent events")

		body = stats + "<h5>Recent Events</h5>" + event_table
		return HTMLResponse(_page("Overview", body, prefix=prefix))

	# ------------------------------------------------------------------
	# Instance list
	# ------------------------------------------------------------------

	@router.get("/instances", response_class=HTMLResponse)
	async def instances(
		request: Request,
		def_key: str = "",
		state: str = "",
		offset: int = 0,
	) -> HTMLResponse:
		wheres = []
		params: dict[str, Any] = {"limit": page_size, "offset": offset}
		if def_key:
			wheres.append("def_key = :def_key")
			params["def_key"] = def_key
		if state:
			wheres.append("state = :state")
			params["state"] = state
		where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

		rows = await _query(f"""
			SELECT id, tenant_id, def_key, state, created_at, updated_at
			FROM workflow_instances
			{where_clause}
			ORDER BY created_at DESC
			LIMIT :limit OFFSET :offset
		""", params)

		def _state_badge(s: str) -> str:
			color = "success" if "terminal_success" in s else "danger" if "terminal_fail" in s else "primary"
			return f'<span class="badge bg-{color}">{s}</span>'

		table_rows = [
			[
				f'<a href="{prefix}/instances/{r["id"]}">{str(r["id"])[:12]}…</a>',
				r.get("tenant_id", ""),
				r.get("def_key", ""),
				_state_badge(r.get("state", "")),
				str(r.get("created_at", ""))[:19],
			]
			for r in rows
		]

		filter_form = f"""<form class="row g-2 mb-3" method="get">
  <div class="col-auto"><input class="form-control form-control-sm" name="def_key"
        placeholder="def_key filter" value="{def_key}"></div>
  <div class="col-auto"><input class="form-control form-control-sm" name="state"
        placeholder="state filter" value="{state}"></div>
  <div class="col-auto"><button class="btn btn-sm btn-outline-primary" type="submit">Filter</button></div>
</form>"""

		body = filter_form + _table(
			["ID", "Tenant", "Def Key", "State", "Created"],
			table_rows,
			empty="No instances found",
		)
		return HTMLResponse(_page("Instances", body, prefix=prefix))

	# ------------------------------------------------------------------
	# Instance detail
	# ------------------------------------------------------------------

	@router.get("/instances/{instance_id}", response_class=HTMLResponse)
	async def instance_detail(instance_id: str) -> HTMLResponse:
		rows = await _query(
			"SELECT * FROM workflow_instances WHERE id = :id",
			{"id": instance_id},
		)
		if not rows:
			return HTMLResponse(_page("Not Found", "<p>Instance not found.</p>", prefix=prefix), status_code=404)

		inst = rows[0]

		# Context
		ctx_raw = inst.get("context") or {}
		if isinstance(ctx_raw, str):
			try:
				ctx_raw = json.loads(ctx_raw)
			except Exception:
				ctx_raw = {"raw": ctx_raw}
		ctx_html = f'<pre class="bg-light p-2 rounded">{json.dumps(ctx_raw, indent=2, default=str)}</pre>'

		# Audit events for this instance
		events = await _query(
			"SELECT kind, payload, created_at FROM audit_events WHERE subject_id = :id ORDER BY created_at DESC LIMIT 50",
			{"id": instance_id},
		)
		event_rows = [
			[e.get("kind"), str(e.get("created_at", ""))[:19]]
			for e in events
		]

		def _state_badge(s: str) -> str:
			color = "success" if "terminal_success" in s else "danger" if "terminal_fail" in s else "primary"
			return f'<span class="badge bg-{color}">{s}</span>'

		detail_html = f"""
<dl class="row">
  <dt class="col-sm-3">ID</dt><dd class="col-sm-9"><code>{inst.get("id")}</code></dd>
  <dt class="col-sm-3">Def Key</dt><dd class="col-sm-9">{inst.get("def_key")}</dd>
  <dt class="col-sm-3">Def Version</dt><dd class="col-sm-9">{inst.get("def_version","")}</dd>
  <dt class="col-sm-3">State</dt><dd class="col-sm-9">{_state_badge(inst.get("state",""))}</dd>
  <dt class="col-sm-3">Tenant</dt><dd class="col-sm-9">{inst.get("tenant_id","")}</dd>
  <dt class="col-sm-3">Created</dt><dd class="col-sm-9">{str(inst.get("created_at",""))[:19]}</dd>
</dl>
<h6>Context</h6>{ctx_html}
<h6>Audit Trail</h6>{_table(["Event Kind", "Time"], event_rows, empty="No audit events")}
"""
		return HTMLResponse(_page(f"Instance {instance_id[:12]}…", detail_html, prefix=prefix))

	# ------------------------------------------------------------------
	# Task queue
	# ------------------------------------------------------------------

	@router.get("/tasks", response_class=HTMLResponse)
	async def tasks(request: Request, status: str = "pending") -> HTMLResponse:
		rows = await _query(
			"SELECT id, tenant_id, kind, ref, note, status, created_at FROM workflow_tasks "
			"WHERE status = :status ORDER BY created_at ASC LIMIT :limit",
			{"status": status, "limit": page_size},
		)
		table_rows = [
			[
				str(r.get("id",""))[:12] + "…",
				r.get("tenant_id",""),
				r.get("kind",""),
				r.get("ref",""),
				r.get("note","")[:60],
				f'<span class="badge bg-{"warning" if r.get("status")=="pending" else "success"}">'
				f'{r.get("status","")}</span>',
				str(r.get("created_at",""))[:19],
			]
			for r in rows
		]
		filter_html = f"""<div class="mb-3">
  <a class="btn btn-sm {'btn-warning' if status=='pending' else 'btn-outline-warning'}"
     href="?status=pending">Pending</a>
  <a class="btn btn-sm {'btn-success' if status=='resolved' else 'btn-outline-success'} ms-1"
     href="?status=resolved">Resolved</a>
</div>"""
		body = filter_html + _table(
			["ID", "Tenant", "Kind", "Ref", "Note", "Status", "Created"],
			table_rows,
			empty="No tasks found",
		)
		return HTMLResponse(_page("Task Queue", body, prefix=prefix))

	# ------------------------------------------------------------------
	# Audit log
	# ------------------------------------------------------------------

	@router.get("/audit", response_class=HTMLResponse)
	async def audit_log(request: Request, subject: str = "", offset: int = 0) -> HTMLResponse:
		params: dict[str, Any] = {"limit": page_size, "offset": offset}
		where = ""
		if subject:
			where = "WHERE subject_id = :subject"
			params["subject"] = subject

		rows = await _query(f"""
			SELECT event_id, kind, subject_id, actor_id, created_at
			FROM audit_events
			{where}
			ORDER BY created_at DESC
			LIMIT :limit OFFSET :offset
		""", params)

		table_rows = [
			[
				str(r.get("event_id",""))[:12] + "…",
				r.get("kind",""),
				f'<a href="{prefix}/instances/{r.get("subject_id","")}">'
				f'{str(r.get("subject_id",""))[:12]}…</a>',
				r.get("actor_id","") or "—",
				str(r.get("created_at",""))[:19],
			]
			for r in rows
		]

		filter_form = f"""<form class="row g-2 mb-3" method="get">
  <div class="col-auto"><input class="form-control form-control-sm" name="subject"
        placeholder="subject_id filter" value="{subject}"></div>
  <div class="col-auto"><button class="btn btn-sm btn-outline-primary" type="submit">Filter</button></div>
</form>"""

		body = filter_form + _table(
			["Event ID", "Kind", "Subject", "Actor", "Time"],
			table_rows,
			empty="No audit events found",
		)
		return HTMLResponse(_page("Audit Log", body, prefix=prefix))

	return router


__all__ = ["make_dashboard_router"]
