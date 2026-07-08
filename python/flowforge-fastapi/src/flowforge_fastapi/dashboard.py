"""Built-in ops dashboard - server-side HTML monitoring UI.

Mount the router returned by :func:`make_dashboard_router` to expose a
live operations dashboard at a configurable prefix (default
``/flowforge/dashboard``).

The dashboard requires a SQLAlchemy ``AsyncSession`` factory that
provides access to the flowforge schema tables (``workflow_instances``,
``workflow_tasks``, ``outbox``, ``audit_events``). It also tolerates the
newer ``ff_audit_events`` table used by ``flowforge-audit-pg``.

Usage::

    from fastapi import FastAPI
    from flowforge_fastapi.dashboard import make_dashboard_router

    app = FastAPI()
    app.include_router(make_dashboard_router(session_factory))

Features
--------
* Overview page: total/active instance counts, pending task count, audit events today
* Instance list: paginated and filterable by state
* Instance detail: current state, context snapshot, history, audit trail
* Task queue: pending/resolved manual-review tasks
* Audit log: recent events, filterable by kind
* Health check: JSON by default, HTML when ``Accept: text/html`` is sent
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML rendering helpers: self-contained CSS/JS, no external dependencies.
# ---------------------------------------------------------------------------

_CSS = r"""
:root {
  color-scheme: light dark;
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-muted: #f1f5f9;
  --text: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
  --shadow-sm: 0 8px 24px rgba(15, 23, 42, 0.06);
  --accent: #4f46e5;
  --accent-strong: #4338ca;
  --accent-soft: #eef2ff;
  --success: #16a34a;
  --success-soft: #dcfce7;
  --warning: #d97706;
  --warning-soft: #fef3c7;
  --danger: #dc2626;
  --danger-soft: #fee2e2;
  --info: #2563eb;
  --info-soft: #dbeafe;
  --neutral: #475569;
  --neutral-soft: #e2e8f0;
  --radius: 8px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #020617;
    --surface: #0f172a;
    --surface-muted: #111827;
    --text: #f8fafc;
    --muted: #94a3b8;
    --border: #1e293b;
    --shadow: 0 22px 55px rgba(0, 0, 0, 0.32);
    --shadow-sm: 0 12px 28px rgba(0, 0, 0, 0.28);
    --accent: #818cf8;
    --accent-strong: #a5b4fc;
    --accent-soft: rgba(99, 102, 241, 0.16);
    --success: #22c55e;
    --success-soft: rgba(34, 197, 94, 0.16);
    --warning: #f59e0b;
    --warning-soft: rgba(245, 158, 11, 0.16);
    --danger: #f87171;
    --danger-soft: rgba(248, 113, 113, 0.16);
    --info: #60a5fa;
    --info-soft: rgba(96, 165, 250, 0.16);
    --neutral: #cbd5e1;
    --neutral-soft: rgba(148, 163, 184, 0.18);
  }
}

* {
  box-sizing: border-box;
}

html {
  min-height: 100%;
}

body {
  min-height: 100%;
  margin: 0;
  background:
    radial-gradient(circle at 18% -12%, rgba(79, 70, 229, 0.12), transparent 34rem),
    linear-gradient(180deg, var(--bg), var(--surface-muted));
  color: var(--text);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}

a {
  color: var(--accent);
  text-decoration: none;
}

a:hover {
  color: var(--accent-strong);
}

.shell {
  min-height: 100vh;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  backdrop-filter: blur(18px);
}

.topbar-inner {
  display: flex;
  align-items: center;
  gap: 1rem;
  width: min(1440px, 100%);
  margin: 0 auto;
  padding: 0.9rem 1rem;
}

.brand {
  display: flex;
  flex-direction: column;
  min-width: 9rem;
}

.brand-title {
  color: var(--text);
  font-size: 1rem;
  font-weight: 760;
  letter-spacing: 0;
}

.brand-subtitle {
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 560;
}

.nav {
  display: flex;
  gap: 0.25rem;
  overflow-x: auto;
  padding: 0.15rem;
}

.nav a {
  display: inline-flex;
  align-items: center;
  min-height: 2.25rem;
  border-radius: 999px;
  padding: 0.45rem 0.8rem;
  color: var(--muted);
  font-size: 0.9rem;
  font-weight: 680;
  transition: background 160ms ease, color 160ms ease, transform 160ms ease;
  white-space: nowrap;
}

.nav a:hover {
  background: var(--surface-muted);
  color: var(--text);
}

.nav a[aria-current="page"] {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.timestamp {
  margin-left: auto;
  color: var(--muted);
  font-size: 0.78rem;
  white-space: nowrap;
}

.page {
  width: min(1440px, 100%);
  margin: 0 auto;
  padding: 1.5rem 1rem 3rem;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.page-kicker {
  margin: 0 0 0.25rem;
  color: var(--accent-strong);
  font-size: 0.76rem;
  font-weight: 780;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1,
h2,
h3 {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: clamp(1.55rem, 4vw, 2.35rem);
  line-height: 1.1;
}

h2 {
  font-size: 1.05rem;
}

h3 {
  font-size: 0.95rem;
}

.section {
  margin-top: 1rem;
}

.grid {
  display: grid;
  gap: 1rem;
}

.grid.stats {
  grid-template-columns: repeat(auto-fit, minmax(13.5rem, 1fr));
}

.grid.two {
  grid-template-columns: 1fr;
}

.card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.card.pad {
  padding: 1rem;
}

.stat-card {
  position: relative;
  overflow: hidden;
  min-height: 9rem;
  padding: 1rem;
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}

.stat-card:hover {
  border-color: color-mix(in srgb, var(--accent) 42%, var(--border));
  box-shadow: var(--shadow);
  transform: translateY(-2px);
}

.stat-label {
  margin: 0;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 760;
  text-transform: uppercase;
}

.stat-value {
  margin-top: 0.65rem;
  color: var(--text);
  font-size: 2.2rem;
  font-weight: 780;
  line-height: 1;
}

.stat-note {
  margin-top: 0.55rem;
  color: var(--muted);
  font-size: 0.88rem;
}

.stat-rail {
  position: absolute;
  inset: 0 auto 0 0;
  width: 0.25rem;
  background: var(--accent);
}

.stat-card[data-tone="success"] .stat-rail {
  background: var(--success);
}

.stat-card[data-tone="warning"] .stat-rail {
  background: var(--warning);
}

.stat-card[data-tone="danger"] .stat-rail {
  background: var(--danger);
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.field {
  display: grid;
  gap: 0.25rem;
}

.field label {
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 720;
}

select,
input {
  min-height: 2.35rem;
  min-width: 10rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  padding: 0.45rem 0.65rem;
}

select:focus,
input:focus {
  outline: 2px solid color-mix(in srgb, var(--accent) 34%, transparent);
  border-color: var(--accent);
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.35rem;
  border: 1px solid transparent;
  border-radius: var(--radius);
  background: var(--accent);
  color: #ffffff;
  cursor: pointer;
  font: inherit;
  font-weight: 720;
  padding: 0.45rem 0.85rem;
  transition: background 160ms ease, border-color 160ms ease, color 160ms ease, transform 160ms ease;
}

.button:hover {
  background: var(--accent-strong);
  color: #ffffff;
  transform: translateY(-1px);
}

.button.secondary {
  border-color: var(--border);
  background: var(--surface);
  color: var(--text);
}

.button.secondary:hover {
  border-color: var(--accent);
  color: var(--accent-strong);
}

.table-card {
  overflow: hidden;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}

th,
td {
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 0.9rem;
  text-align: left;
  vertical-align: middle;
}

th {
  background: var(--surface-muted);
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 780;
  text-transform: uppercase;
}

td {
  color: var(--text);
  font-size: 0.9rem;
}

tr.clickable-row {
  cursor: pointer;
}

tbody tr {
  transition: background 140ms ease;
}

tbody tr:hover {
  background: var(--surface-muted);
}

tbody tr:last-child td {
  border-bottom: 0;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

.muted {
  color: var(--muted);
}

.pill,
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 1.55rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 760;
  line-height: 1;
  padding: 0.28rem 0.55rem;
  white-space: nowrap;
}

.pill[data-tone="success"],
.badge[data-tone="success"] {
  background: var(--success-soft);
  color: var(--success);
}

.pill[data-tone="warning"],
.badge[data-tone="warning"] {
  background: var(--warning-soft);
  color: var(--warning);
}

.pill[data-tone="danger"],
.badge[data-tone="danger"] {
  background: var(--danger-soft);
  color: var(--danger);
}

.pill[data-tone="info"],
.badge[data-tone="info"] {
  background: var(--info-soft);
  color: var(--info);
}

.pill[data-tone="neutral"],
.badge[data-tone="neutral"] {
  background: var(--neutral-soft);
  color: var(--neutral);
}

.timeline {
  display: grid;
  gap: 0.85rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.timeline-item {
  display: grid;
  grid-template-columns: 0.8rem 1fr;
  gap: 0.75rem;
}

.timeline-dot {
  width: 0.7rem;
  height: 0.7rem;
  margin-top: 0.42rem;
  border: 2px solid var(--surface);
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.timeline-title {
  font-weight: 740;
}

.timeline-meta {
  color: var(--muted);
  font-size: 0.84rem;
}

.empty {
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  color: var(--muted);
  padding: 1.2rem;
  text-align: center;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 1rem;
}

.pagination .buttons {
  display: flex;
  gap: 0.5rem;
}

.disabled {
  opacity: 0.5;
  pointer-events: none;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

.kv {
  display: grid;
  grid-template-columns: minmax(8rem, 14rem) 1fr;
  gap: 0.55rem 1rem;
  margin: 0;
}

.kv dt {
  color: var(--muted);
  font-weight: 720;
}

.kv dd {
  margin: 0;
}

pre {
  overflow: auto;
  max-height: 36rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted);
  color: var(--text);
  font-size: 0.85rem;
  padding: 1rem;
}

@media (min-width: 900px) {
  .grid.two {
    grid-template-columns: minmax(0, 1.4fr) minmax(18rem, 0.6fr);
  }

  .detail-grid {
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  }
}

@media (max-width: 760px) {
  .topbar-inner {
    align-items: flex-start;
    flex-direction: column;
  }

  .timestamp {
    margin-left: 0;
  }

  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .pagination {
    align-items: flex-start;
    flex-direction: column;
  }

  .kv {
    grid-template-columns: 1fr;
  }
}
"""

_JS = r"""
document.addEventListener("DOMContentLoaded", () => {
  for (const row of document.querySelectorAll("[data-href]")) {
    row.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input, select, textarea")) return;
      window.location.href = row.dataset.href;
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        window.location.href = row.dataset.href;
      }
    });
  }
});
"""


def _h(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _format_ts(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return _h(value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    text = str(value).replace("T", " ")
    return _h(text[:19])


def _short(value: Any, *, length: int = 12) -> str:
    text = "" if value is None else str(value)
    if len(text) <= length:
        return _h(text)
    return _h(text[:length] + "...")


def _json_block(value: Any) -> str:
    try:
        text = json.dumps(value, indent=2, sort_keys=True, default=str)
    except TypeError:
        text = json.dumps({"raw": str(value)}, indent=2)
    return f'<pre>{_h(text)}</pre>'


def _metric_card(label: str, value: Any, note: str, *, tone: str = "info") -> str:
    return f"""<article class="card stat-card" data-tone="{_h(tone)}">
  <div class="stat-rail"></div>
  <p class="stat-label">{_h(label)}</p>
  <div class="stat-value">{_h(value)}</div>
  <div class="stat-note">{_h(note)}</div>
</article>"""


def _tone_for_state(state: str) -> str:
    normalized = state.strip().lower()
    if any(marker in normalized for marker in ("error", "fail", "failed")):
        return "danger"
    if normalized in {"complete", "completed", "done", "success"} or normalized.startswith("terminal"):
        return "neutral"
    if "pending" in normalized or normalized in {"queued", "new"}:
        return "info"
    if normalized in {"active", "running", "in_progress"} or normalized:
        return "success"
    return "neutral"


def _tone_for_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"ok", "active", "running", "resolved", "dispatched", "success"}:
        return "success"
    if normalized in {"pending", "queued", "retry", "retried", "in_flight"}:
        return "warning"
    if normalized in {"dead", "error", "failed", "degraded"}:
        return "danger"
    return "neutral"


def _badge(label: Any, *, tone: str = "neutral") -> str:
    return f'<span class="badge" data-tone="{_h(tone)}">{_h(label)}</span>'


def _state_badge(state: Any) -> str:
    text = "" if state is None else str(state)
    return _badge(text or "unknown", tone=_tone_for_state(text))


def _status_pill(label: str, *, tone: str) -> str:
    return f'<span class="pill" data-tone="{_h(tone)}">{_h(label)}</span>'


def _table(
    headers: list[str],
    rows: list[list[str]],
    *,
    empty: str = "No data",
    row_hrefs: list[str] | None = None,
) -> str:
    if not rows:
        return f'<div class="empty">{_h(empty)}</div>'
    head = "".join(f"<th>{_h(header)}</th>" for header in headers)
    body = []
    for index, row in enumerate(rows):
        href = row_hrefs[index] if row_hrefs and index < len(row_hrefs) else ""
        attrs = (
            f' class="clickable-row" tabindex="0" data-href="{_h(href)}"'
            if href
            else ""
        )
        cells = "".join(f"<td>{cell}</td>" for cell in row)
        body.append(f"<tr{attrs}>{cells}</tr>")
    return f"""<div class="card table-card">
  <div class="table-scroll">
    <table>
      <thead><tr>{head}</tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
  </div>
</div>"""


def _query_link(path: str, params: Mapping[str, Any]) -> str:
    clean = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }
    query = urlencode(clean)
    return path + (f"?{query}" if query else "")


def _pagination(
    *,
    path: str,
    page: int,
    limit: int,
    total: int,
    extra: Mapping[str, Any] | None = None,
) -> str:
    extra_params = dict(extra or {})
    last_page = max(1, (int(total) + limit - 1) // limit) if total else 1
    prev_page = max(1, page - 1)
    next_page = min(last_page, page + 1)
    prev_href = _query_link(path, {**extra_params, "page": prev_page, "limit": limit})
    next_href = _query_link(path, {**extra_params, "page": next_page, "limit": limit})
    prev_class = "button secondary disabled" if page <= 1 else "button secondary"
    next_class = "button secondary disabled" if page >= last_page else "button secondary"
    start = 0 if total == 0 else ((page - 1) * limit) + 1
    end = min(total, page * limit)
    return f"""<nav class="pagination" aria-label="Pagination">
  <div class="muted">Rows {_h(start)}-{_h(end)} of {_h(total)} - Page {_h(page)} of {_h(last_page)}</div>
  <div class="buttons">
    <a class="{prev_class}" href="{_h(prev_href)}">Previous</a>
    <a class="{next_class}" href="{_h(next_href)}">Next</a>
  </div>
</nav>"""


def _render_page(
    title: str,
    content: str,
    active_nav: str,
    *,
    prefix: str = "/flowforge/dashboard",
    auto_refresh_seconds: int | None = None,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    refresh_meta = (
        f'\n  <meta http-equiv="refresh" content="{int(auto_refresh_seconds)}">'
        if auto_refresh_seconds
        else ""
    )
    nav_items = [
        ("overview", "Overview", prefix + "/"),
        ("instances", "Instances", prefix + "/instances"),
        ("tasks", "Tasks", prefix + "/tasks"),
        ("audit", "Audit", prefix + "/audit"),
        ("health", "Health", prefix + "/health"),
    ]
    nav_parts = []
    for key, label, href in nav_items:
        current_attr = ' aria-current="page"' if key == active_nav else ""
        nav_parts.append(f'<a href="{_h(href)}"{current_attr}>{_h(label)}</a>')
    nav = "".join(nav_parts)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">{refresh_meta}
  <title>{_h(title)} - flowforge</title>
  <style>{_CSS}</style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="{_h(prefix + '/')}">
          <span class="brand-title">flowforge</span>
          <span class="brand-subtitle">Operations Dashboard</span>
        </a>
        <nav class="nav" aria-label="Dashboard">{nav}</nav>
        <div class="timestamp">{_h(now)}</div>
      </div>
    </header>
    <main class="page">
      <div class="page-header">
        <div>
          <p class="page-kicker">flowforge</p>
          <h1>{_h(title)}</h1>
        </div>
      </div>
      {content}
    </main>
  </div>
  <script>{_JS}</script>
</body>
</html>"""


def _normalize_page(page: int, limit: int, page_size: int) -> tuple[int, int, int]:
    safe_limit = max(1, min(int(limit or page_size), 200))
    safe_page = max(1, int(page or 1))
    return safe_page, safe_limit, (safe_page - 1) * safe_limit


def _health_tone(*, pending_tasks: int, outbox_backlog: int, error_instances: int) -> tuple[str, str]:
    if error_instances > 0 or outbox_backlog >= 250:
        return "red", "danger"
    if pending_tasks > 0 or outbox_backlog > 0:
        return "amber", "warning"
    return "green", "success"


def _row_to_dict(row: Any, columns: list[str]) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return dict(mapping)
    return dict(zip(columns, row))


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def make_dashboard_router(
    session_factory: Callable,
    *,
    prefix: str = "/flowforge/dashboard",
    page_size: int = 50,
    worker_pool: Any | None = None,
) -> APIRouter:
    """Create a FastAPI router serving the ops dashboard.

    Args:
        session_factory: An async SQLAlchemy session factory (``async_sessionmaker``
            or any ``async with session_factory() as s`` compatible callable).
        prefix: URL prefix for all dashboard routes.
        page_size: Max rows per page on list views.
        worker_pool: Optional outbox worker/pool object exposing ``health()``.
    """

    router = APIRouter(prefix=prefix, tags=["flowforge-dashboard"])

    async def _query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a raw SQL query and return row dictionaries."""

        from sqlalchemy import text

        try:
            async with session_factory() as session:
                result = await session.execute(text(sql), params or {})
                columns = list(result.keys())
                return [_row_to_dict(row, columns) for row in result.fetchall()]
        except Exception as exc:
            _log.debug("dashboard query failed: %s | sql=%r", exc, sql)
            return []

    async def _query_first(
        candidates: list[str],
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        for sql in candidates:
            rows = await _query(sql, params)
            if rows:
                return rows
        return []

    async def _scalar(sql: str, params: dict[str, Any] | None = None, *, default: Any = 0) -> Any:
        """Execute a scalar SQL query."""

        from sqlalchemy import text

        try:
            async with session_factory() as session:
                result = await session.execute(text(sql), params or {})
                value = result.scalar()
                return value if value is not None else default
        except Exception as exc:
            _log.debug("dashboard scalar failed: %s | sql=%r", exc, sql)
            return default

    async def _scalar_first(
        candidates: list[str],
        params: dict[str, Any] | None = None,
        *,
        default: Any = 0,
    ) -> Any:
        sentinel = object()
        for sql in candidates:
            value = await _scalar(sql, params, default=sentinel)
            if value is not sentinel:
                return value
        return default

    async def _audit_rows(
        *,
        limit: int,
        offset: int = 0,
        kind: str = "",
        subject_id: str = "",
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if kind:
            where_parts.append("kind = :kind")
            params["kind"] = kind
        if subject_id:
            where_parts.append("subject_id = :subject_id")
            params["subject_id"] = subject_id
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        legacy_subject_where = ""
        legacy_params = dict(params)
        if kind:
            legacy_subject_where = "WHERE kind = :kind"
        if subject_id:
            legacy_subject_where = (
                (legacy_subject_where + " AND ") if legacy_subject_where else "WHERE "
            ) + "subject_id = :subject_id"

        workflow_where_parts: list[str] = []
        workflow_params = dict(params)
        if kind:
            workflow_where_parts.append("event = :kind")
        if subject_id:
            workflow_where_parts.append("instance_id = :subject_id")
        workflow_where = (
            "WHERE " + " AND ".join(workflow_where_parts) if workflow_where_parts else ""
        )

        return await _query_first(
            [
                f"""
                SELECT kind, subject_kind, subject_id, actor_user_id, occurred_at
                FROM audit_events
                {where}
                ORDER BY occurred_at DESC
                LIMIT :limit OFFSET :offset
                """,
                f"""
                SELECT kind, '' AS subject_kind, subject_id, actor_id AS actor_user_id,
                       created_at AS occurred_at
                FROM audit_events
                {legacy_subject_where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """,
                f"""
                SELECT kind, subject_kind, subject_id, actor_user_id, occurred_at
                FROM ff_audit_events
                {where}
                ORDER BY occurred_at DESC
                LIMIT :limit OFFSET :offset
                """,
                f"""
                SELECT event AS kind, 'workflow' AS subject_kind,
                       instance_id AS subject_id, actor_user_id, occurred_at
                FROM workflow_events
                {workflow_where}
                ORDER BY occurred_at DESC
                LIMIT :limit OFFSET :offset
                """,
            ],
            legacy_params if legacy_subject_where else params if not workflow_where else workflow_params,
        )

    async def _audit_count(*, kind: str = "") -> int:
        params = {"kind": kind} if kind else {}
        where = "WHERE kind = :kind" if kind else ""
        workflow_where = "WHERE event = :kind" if kind else ""
        value = await _scalar_first(
            [
                f"SELECT COUNT(*) FROM audit_events {where}",
                f"SELECT COUNT(*) FROM ff_audit_events {where}",
                f"SELECT COUNT(*) FROM workflow_events {workflow_where}",
            ],
            params,
            default=0,
        )
        return int(value or 0)

    async def _worker_pool_health() -> dict[str, Any]:
        if worker_pool is None:
            return {
                "status": "unavailable",
                "workers": 0,
                "last_run_at": None,
                "last_result": {},
                "run_errors": 0,
            }
        try:
            health_obj = worker_pool.health() if hasattr(worker_pool, "health") else worker_pool
            if inspect.isawaitable(health_obj):
                health_obj = await health_obj
            if hasattr(health_obj, "as_dict"):
                data = dict(health_obj.as_dict())
            elif isinstance(health_obj, Mapping):
                data = dict(health_obj)
            else:
                data = {
                    name: getattr(health_obj, name)
                    for name in dir(health_obj)
                    if not name.startswith("_") and not callable(getattr(health_obj, name))
                }
            if "workers" in data and "n_workers" in data:
                data["workers"] = data.get("n_workers")
            return data
        except Exception as exc:
            _log.debug("dashboard worker_pool health failed: %s", exc)
            return {
                "status": "degraded",
                "workers": 0,
                "last_run_at": None,
                "last_result": {},
                "run_errors": 1,
                "last_error": str(exc),
            }

    async def _overview_stats() -> dict[str, int]:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        total_instances = int(await _scalar("SELECT COUNT(*) FROM workflow_instances") or 0)
        active_instances = int(
            await _scalar(
                """
                SELECT COUNT(*)
                FROM workflow_instances
                WHERE state NOT LIKE 'terminal%'
                  AND lower(state) NOT IN ('complete', 'completed', 'done', 'success', 'error', 'failed')
                """
            )
            or 0
        )
        error_instances = int(
            await _scalar(
                """
                SELECT COUNT(*)
                FROM workflow_instances
                WHERE lower(state) LIKE '%error%' OR lower(state) LIKE '%fail%'
                """
            )
            or 0
        )
        pending_tasks = int(
            await _scalar("SELECT COUNT(*) FROM workflow_tasks WHERE status = 'pending'") or 0
        )
        audit_today = int(
            await _scalar_first(
                [
                    "SELECT COUNT(*) FROM audit_events WHERE occurred_at >= :today_start",
                    "SELECT COUNT(*) FROM audit_events WHERE created_at >= :today_start",
                    "SELECT COUNT(*) FROM ff_audit_events WHERE occurred_at >= :today_start",
                    "SELECT COUNT(*) FROM workflow_events WHERE occurred_at >= :today_start",
                ],
                {"today_start": today_start},
                default=0,
            )
            or 0
        )
        outbox_backlog = int(
            await _scalar("SELECT COUNT(*) FROM outbox WHERE status = 'pending'") or 0
        )
        return {
            "total_instances": total_instances,
            "active_instances": active_instances,
            "error_instances": error_instances,
            "pending_tasks": pending_tasks,
            "audit_today": audit_today,
            "outbox_backlog": outbox_backlog,
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @router.get("/health", response_model=None)
    async def health(request: Request) -> Response:
        """Return JSON by default, or HTML when requested by a browser."""

        stats = await _overview_stats()
        outbox_rows = await _query(
            """
            SELECT status, COUNT(*) AS count
            FROM outbox
            GROUP BY status
            ORDER BY status
            """
        )
        last_drain_time = await _scalar(
            "SELECT MAX(created_at) FROM outbox WHERE status != 'pending'",
            default=None,
        )
        worker_health = await _worker_pool_health()
        health_label, health_tone = _health_tone(
            pending_tasks=stats["pending_tasks"],
            outbox_backlog=stats["outbox_backlog"],
            error_instances=stats["error_instances"],
        )
        payload = {
            "status": "ok" if health_label == "green" else "degraded",
            "running_instances": stats["active_instances"],
            "pending_tasks": stats["pending_tasks"],
            "outbox_backlog": stats["outbox_backlog"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker_pool": worker_health,
            "outbox_by_status": {str(row.get("status", "")): row.get("count", 0) for row in outbox_rows},
            "last_drain_time": last_drain_time,
        }

        if "text/html" not in request.headers.get("accept", "").lower():
            return JSONResponse(payload)

        status_rows = [
            [
                _badge(row.get("status") or "unknown", tone=_tone_for_status(str(row.get("status", "")))),
                _h(row.get("count", 0)),
            ]
            for row in outbox_rows
        ]
        if not status_rows:
            status_rows = [[_badge("empty", tone="neutral"), "0"]]

        worker_last_result = worker_health.get("last_result") or {}
        worker_status = str(worker_health.get("status", "unavailable"))
        worker_count = worker_health.get("workers", worker_health.get("n_workers", 0))
        content = f"""<section class="grid stats">
  {_metric_card("System health", health_label, "Composite DB signal", tone=health_tone)}
  {_metric_card("Outbox queue depth", stats["outbox_backlog"], "Pending messages", tone="warning" if stats["outbox_backlog"] else "success")}
  {_metric_card("Worker pool", worker_count, "Status: " + worker_status, tone=_tone_for_status(worker_status))}
  {_metric_card("Last drain time", _format_ts(last_drain_time) or "unseen", "Newest non-pending outbox row", tone="info")}
</section>
<section class="grid two section">
  <div>
    <h2>Outbox Status</h2>
    {_table(["Status", "Rows"], status_rows, empty="No outbox rows")}
  </div>
  <article class="card pad">
    <h2>Worker Pool Stats</h2>
    <dl class="kv">
      <dt>Status</dt><dd>{_badge(worker_status, tone=_tone_for_status(worker_status))}</dd>
      <dt>Workers</dt><dd>{_h(worker_count)}</dd>
      <dt>Last run</dt><dd>{_format_ts(worker_health.get("last_run_at")) or '<span class="muted">unseen</span>'}</dd>
      <dt>Run errors</dt><dd>{_h(worker_health.get("run_errors", 0))}</dd>
      <dt>Last result</dt><dd class="mono">{_h(worker_last_result)}</dd>
    </dl>
  </article>
</section>"""
        return HTMLResponse(_render_page("Health", content, "health", prefix=prefix))

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------

    @router.get("/", response_class=HTMLResponse)
    async def overview(request: Request) -> HTMLResponse:
        stats = await _overview_stats()
        health_label, health_tone = _health_tone(
            pending_tasks=stats["pending_tasks"],
            outbox_backlog=stats["outbox_backlog"],
            error_instances=stats["error_instances"],
        )
        recent_events = await _audit_rows(limit=10)
        timeline = "".join(
            f"""<li class="timeline-item">
  <span class="timeline-dot"></span>
  <div>
    <div class="timeline-title">{_h(event.get("kind", ""))}</div>
    <div class="timeline-meta">
      {_h(event.get("subject_kind", "") or "subject")} / {_short(event.get("subject_id", ""))}
      - {_format_ts(event.get("occurred_at"))}
    </div>
  </div>
</li>"""
            for event in recent_events
        )
        activity = (
            f'<ol class="timeline">{timeline}</ol>'
            if recent_events
            else '<div class="empty">No recent audit events</div>'
        )
        content = f"""<section class="grid stats">
  {_metric_card("Total instances", stats["total_instances"], "All workflow instances", tone="info")}
  {_metric_card("Active instances", stats["active_instances"], "Non-terminal work in progress", tone="success")}
  {_metric_card("Tasks pending", stats["pending_tasks"], "Manual review queue", tone="warning" if stats["pending_tasks"] else "success")}
  {_metric_card("Audit events today", stats["audit_today"], "UTC day boundary", tone="info")}
</section>
<section class="grid two section">
  <article class="card pad">
    <h2>Recent Activity</h2>
    {activity}
  </article>
  <article class="card pad">
    <h2>System Health</h2>
    <dl class="kv">
      <dt>Status</dt><dd>{_status_pill(health_label, tone=health_tone)}</dd>
      <dt>Outbox backlog</dt><dd>{_h(stats["outbox_backlog"])}</dd>
      <dt>Error states</dt><dd>{_h(stats["error_instances"])}</dd>
      <dt>Pending tasks</dt><dd>{_h(stats["pending_tasks"])}</dd>
    </dl>
  </article>
</section>"""
        return HTMLResponse(
            _render_page(
                "Overview",
                content,
                "overview",
                prefix=prefix,
                auto_refresh_seconds=30,
            )
        )

    # ------------------------------------------------------------------
    # Instance list
    # ------------------------------------------------------------------

    @router.get("/instances", response_class=HTMLResponse)
    async def instances(
        request: Request,
        state: str = "",
        page: int = 1,
        limit: int = 0,
    ) -> HTMLResponse:
        page, limit, offset = _normalize_page(page, limit, page_size)
        where = "WHERE state = :state" if state else ""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        count_params: dict[str, Any] = {}
        if state:
            params["state"] = state
            count_params["state"] = state

        rows = await _query(
            f"""
            SELECT id, def_key AS workflow_def, state, tenant_id, created_at, updated_at
            FROM workflow_instances
            {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """,
            params,
        )
        total = int(
            await _scalar(
                f"SELECT COUNT(*) FROM workflow_instances {where}",
                count_params,
            )
            or 0
        )
        state_rows = await _query(
            "SELECT DISTINCT state FROM workflow_instances ORDER BY state"
        )
        state_options = ["", "pending", "active", "error", "complete"]
        for row in state_rows:
            value = str(row.get("state", ""))
            if value and value not in state_options:
                state_options.append(value)
        if state and state not in state_options:
            state_options.append(state)
        options = "".join(
            f'<option value="{_h(value)}"{" selected" if value == state else ""}>'
            f'{_h(value or "All states")}</option>'
            for value in state_options
        )
        table_rows = [
            [
                f'<a class="mono" href="{_h(prefix + "/instances/" + str(row.get("id", "")))}">{_short(row.get("id"))}</a>',
                _h(row.get("workflow_def", "")),
                _state_badge(row.get("state", "")),
                _h(row.get("tenant_id", "")),
                _format_ts(row.get("created_at")),
                _format_ts(row.get("updated_at")),
            ]
            for row in rows
        ]
        row_hrefs = [prefix + "/instances/" + str(row.get("id", "")) for row in rows]
        content = f"""<form class="toolbar" method="get">
  <div class="field">
    <label for="state">State</label>
    <select id="state" name="state">{options}</select>
  </div>
  <div class="field">
    <label for="limit">Limit</label>
    <input id="limit" name="limit" type="number" min="1" max="200" value="{_h(limit)}">
  </div>
  <input type="hidden" name="page" value="1">
  <button class="button" type="submit">Filter</button>
  <a class="button secondary" href="{_h(prefix + "/instances")}">Reset</a>
</form>
{_table(["ID", "workflow_def", "State", "tenant_id", "created_at", "updated_at"], table_rows, empty="No instances found", row_hrefs=row_hrefs)}
{_pagination(path=prefix + "/instances", page=page, limit=limit, total=total, extra={"state": state})}"""
        return HTMLResponse(_render_page("Instances", content, "instances", prefix=prefix))

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
            content = '<div class="empty">Instance not found</div>'
            return HTMLResponse(
                _render_page("Instance Not Found", content, "instances", prefix=prefix),
                status_code=404,
            )

        inst = rows[0]
        ctx_raw = inst.get("context") or {}
        if isinstance(ctx_raw, str):
            try:
                ctx_raw = json.loads(ctx_raw)
            except Exception:
                ctx_raw = {"raw": ctx_raw}

        events = await _audit_rows(limit=50, subject_id=instance_id)
        event_rows = [
            [
                _h(row.get("kind", "")),
                _h(row.get("subject_kind", "")),
                _h(row.get("actor_user_id", "") or "-"),
                _format_ts(row.get("occurred_at")),
            ]
            for row in events
        ]
        content = f"""<section class="detail-grid">
  <article class="card pad">
    <h2>Instance</h2>
    <dl class="kv">
      <dt>ID</dt><dd class="mono">{_h(inst.get("id"))}</dd>
      <dt>workflow_def</dt><dd>{_h(inst.get("def_key", ""))}</dd>
      <dt>Version</dt><dd>{_h(inst.get("def_version", ""))}</dd>
      <dt>State</dt><dd>{_state_badge(inst.get("state", ""))}</dd>
      <dt>tenant_id</dt><dd>{_h(inst.get("tenant_id", ""))}</dd>
      <dt>created_at</dt><dd>{_format_ts(inst.get("created_at"))}</dd>
      <dt>updated_at</dt><dd>{_format_ts(inst.get("updated_at"))}</dd>
    </dl>
  </article>
  <article class="card pad">
    <h2>Context</h2>
    {_json_block(ctx_raw)}
  </article>
</section>
<section class="section">
  <h2>Audit Trail</h2>
  {_table(["Kind", "subject_kind", "actor_user_id", "occurred_at"], event_rows, empty="No audit events")}
</section>"""
        return HTMLResponse(
            _render_page(f"Instance {_short(instance_id)}", content, "instances", prefix=prefix)
        )

    # ------------------------------------------------------------------
    # Task queue
    # ------------------------------------------------------------------

    @router.get("/tasks", response_class=HTMLResponse)
    async def tasks(request: Request, status: str = "pending") -> HTMLResponse:
        rows = await _query(
            """
            SELECT id, tenant_id, kind, ref, note, status, created_at, resolved_at
            FROM workflow_tasks
            WHERE status = :status
            ORDER BY created_at ASC
            LIMIT :limit
            """,
            {"status": status, "limit": page_size},
        )
        table_rows = [
            [
                f'<span class="mono">{_short(row.get("id"))}</span>',
                _h(row.get("tenant_id", "")),
                _h(row.get("kind", "")),
                _h(row.get("ref", "")),
                _h(str(row.get("note", ""))[:80]),
                _badge(row.get("status", ""), tone=_tone_for_status(str(row.get("status", "")))),
                _format_ts(row.get("created_at")),
                _format_ts(row.get("resolved_at")),
            ]
            for row in rows
        ]
        pending_href = prefix + "/tasks?status=pending"
        resolved_href = prefix + "/tasks?status=resolved"
        content = f"""<div class="toolbar">
  <a class="button{' secondary' if status != 'pending' else ''}" href="{_h(pending_href)}">Pending</a>
  <a class="button{' secondary' if status != 'resolved' else ''}" href="{_h(resolved_href)}">Resolved</a>
</div>
{_table(["ID", "tenant_id", "Kind", "Ref", "Note", "Status", "created_at", "resolved_at"], table_rows, empty="No tasks found")}"""
        return HTMLResponse(_render_page("Tasks", content, "tasks", prefix=prefix))

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    @router.get("/audit", response_class=HTMLResponse)
    async def audit_log(
        request: Request,
        kind: str = "",
        page: int = 1,
        limit: int = 0,
    ) -> HTMLResponse:
        page, limit, offset = _normalize_page(page, limit, page_size)
        rows = await _audit_rows(limit=limit, offset=offset, kind=kind)
        total = await _audit_count(kind=kind)
        kind_rows = await _query_first(
            [
                "SELECT DISTINCT kind FROM audit_events ORDER BY kind",
                "SELECT DISTINCT kind FROM ff_audit_events ORDER BY kind",
                "SELECT DISTINCT event AS kind FROM workflow_events ORDER BY event",
            ]
        )
        kind_options = [""]
        for row in kind_rows:
            value = str(row.get("kind", ""))
            if value and value not in kind_options:
                kind_options.append(value)
        if kind and kind not in kind_options:
            kind_options.append(kind)
        options = "".join(
            f'<option value="{_h(value)}"{" selected" if value == kind else ""}>'
            f'{_h(value or "All kinds")}</option>'
            for value in kind_options
        )
        table_rows = [
            [
                _h(row.get("kind", "")),
                _h(row.get("subject_kind", "")),
                f'<a class="mono" href="{_h(prefix + "/instances/" + str(row.get("subject_id", "")))}">{_short(row.get("subject_id"))}</a>',
                _h(row.get("actor_user_id", "") or "-"),
                _format_ts(row.get("occurred_at")),
            ]
            for row in rows
        ]
        content = f"""<form class="toolbar" method="get">
  <div class="field">
    <label for="kind">Kind</label>
    <select id="kind" name="kind">{options}</select>
  </div>
  <div class="field">
    <label for="limit">Limit</label>
    <input id="limit" name="limit" type="number" min="1" max="200" value="{_h(limit)}">
  </div>
  <input type="hidden" name="page" value="1">
  <button class="button" type="submit">Filter</button>
  <a class="button secondary" href="{_h(prefix + "/audit")}">Reset</a>
</form>
{_table(["kind", "subject_kind", "subject_id", "actor_user_id", "occurred_at"], table_rows, empty="No audit events found")}
{_pagination(path=prefix + "/audit", page=page, limit=limit, total=total, extra={"kind": kind})}"""
        return HTMLResponse(_render_page("Audit", content, "audit", prefix=prefix))

    return router


__all__ = ["make_dashboard_router"]
