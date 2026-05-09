"""Per-bundle generator: emit a tenant-scoped admin console React app.

Item 15 of :doc:`docs/improvements`, W2 sub-batch 2b of
:doc:`docs/v0.3.0-engineering-plan`.

The admin console is a standalone Vite + React 18 single-page app
(distinct from the customer-facing ``frontend/`` Next.js app emitted by
:mod:`.frontend`). It surveys all JTBDs in the bundle from the
operator's perspective and surfaces six panels:

* **Instance browser** — list entities, filter by JTBD/state/tenant.
* **Audit-log viewer** — calls ``AuditSink.verify_chain()`` and shows
  hash-chain integrity status per topic.
* **Saga compensation panel** — pending compensations + manual trigger
  guarded by an ``admin.<jtbd>.compensate`` permission. Until item 12
  (OTel) ships the per-saga span list shows "no spans recorded".
* **Permission-grant history** — who granted what to whom, when
  (sourced from ``AccessGrantPort``).
* **Deferred outbox queue** — envelopes pending dispatch + retry status
  (sourced from ``OutboxRegistry``).
* **RLS elevation log** — records of ``elevation_scope()`` calls
  (sourced from the audit chain's ``rls.elevate`` topic).

Why a separate React app: the operator console's threat model and UX
brief diverge sharply from the customer flow (granular ADMIN_*
permissions, sortable tables, hash-chain verification UI). Coupling
them through Next.js routing would force operators onto the customer
build and visa versa. A standalone Vite SPA keeps the admin app
deployable in isolation behind a separate ingress / auth proxy.

Postgres assumption: the back-end endpoints the admin app calls are
implemented by Postgres-backed adapters today (``flowforge-audit-pg``,
``flowforge-outbox-pg``, plus the bundle's own SQLAlchemy models).
Non-PG hosts must wire equivalent ``AuditSink`` /
``OutboxRegistry`` adapters before deploying the console; the generated
README spells this out.

Determinism: every emitted file is rendered from a jinja2 template
with sorted dict iteration over JTBDs. Two regens of the same bundle
produce byte-identical output (Principle 1).
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"all_audit_topics",
	"jtbds[].class_name",
	"jtbds[].id",
	"jtbds[].permissions",
	"jtbds[].title",
	"jtbds[].url_segment",
	"project.name",
	"project.package",
	"project.tenancy",
)


# Static set of admin pages the generator emits. Listed once here so the
# router, sidebar, and registry tests all agree on the canonical order.
_PAGE_NAMES: tuple[str, ...] = (
	"instances",
	"audit",
	"saga",
	"grants",
	"outbox",
	"rls",
)


# Template files emitted at the admin app's root. Paths are relative to
# ``frontend-admin/<package>/``. Each entry is ``(template, dest)``.
_ROOT_TEMPLATES: tuple[tuple[str, str], ...] = (
	("frontend_admin/package.json.j2", "package.json"),
	("frontend_admin/tsconfig.json.j2", "tsconfig.json"),
	("frontend_admin/vite.config.ts.j2", "vite.config.ts"),
	("frontend_admin/index.html.j2", "index.html"),
	("frontend_admin/README.md.j2", "README.md"),
)


# Template files emitted under ``src/``. Same shape as ``_ROOT_TEMPLATES``.
_SRC_TEMPLATES: tuple[tuple[str, str], ...] = (
	("frontend_admin/src/main.tsx.j2", "src/main.tsx"),
	("frontend_admin/src/App.tsx.j2", "src/App.tsx"),
	("frontend_admin/src/api.ts.j2", "src/api.ts"),
	("frontend_admin/src/permissions.ts.j2", "src/permissions.ts"),
	("frontend_admin/src/pages/InstanceBrowser.tsx.j2", "src/pages/InstanceBrowser.tsx"),
	("frontend_admin/src/pages/AuditLogViewer.tsx.j2", "src/pages/AuditLogViewer.tsx"),
	("frontend_admin/src/pages/SagaPanel.tsx.j2", "src/pages/SagaPanel.tsx"),
	("frontend_admin/src/pages/PermissionsHistory.tsx.j2", "src/pages/PermissionsHistory.tsx"),
	("frontend_admin/src/pages/OutboxQueue.tsx.j2", "src/pages/OutboxQueue.tsx"),
	("frontend_admin/src/pages/RlsLog.tsx.j2", "src/pages/RlsLog.tsx"),
)


def _admin_permissions(bundle: NormalizedBundle) -> tuple[str, ...]:
	"""Synthesize the closed set of ``admin.*`` permissions for *bundle*.

	For every JTBD the bundle declares we synthesize four operator-side
	permissions: ``admin.<id>.read`` (broad audit), ``admin.<id>.compensate``
	(saga rollback trigger), ``admin.<id>.outbox.retry`` (envelope retry),
	and ``admin.<id>.grant`` (grant/revoke access). These mirror the W0
	permissions catalog's per-JTBD granularity without requiring a
	bundle-schema change.

	Sorted for deterministic emission across runs.
	"""

	out: set[str] = set()
	for jt in bundle.jtbds:
		out.add(f"admin.{jt.id}.read")
		out.add(f"admin.{jt.id}.compensate")
		out.add(f"admin.{jt.id}.outbox.retry")
		out.add(f"admin.{jt.id}.grant")
	return tuple(sorted(out))


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit the admin console as a per-bundle directory tree.

	All files land under ``frontend-admin/<project.package>/`` so two
	bundles can coexist in the same monorepo without colliding.
	"""

	pkg = bundle.project.package
	root = f"frontend-admin/{pkg}"
	admin_perms = _admin_permissions(bundle)
	jtbds_sorted = tuple(sorted(bundle.jtbds, key=lambda j: j.id))

	context: dict[str, object] = {
		"project": bundle.project,
		"bundle": bundle,
		"jtbds": jtbds_sorted,
		"admin_permissions": admin_perms,
		"page_names": _PAGE_NAMES,
	}

	files: list[GeneratedFile] = []
	for tpl, rel in _ROOT_TEMPLATES + _SRC_TEMPLATES:
		content = render(tpl, **context)
		files.append(GeneratedFile(path=f"{root}/{rel}", content=content))
	return files
