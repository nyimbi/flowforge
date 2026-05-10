"""Per-bundle generator: emit an email-driven adapter shell.

Item 9 of :doc:`docs/improvements`, W3 of
:doc:`docs/v0.3.0-engineering-plan`.

The email adapter is a standalone Python package distinct from
:mod:`.frontend` (Next.js customer surface), :mod:`.frontend_admin`
(operator console SPA), :mod:`.frontend_cli` (Typer CLI client) and
:mod:`.frontend_slack` (Slack adapter shell). It exposes:

* an inbound parser ABC that turns a parsed RFC-5322 message into a
  ``(jtbd, event, payload)`` triple — the reply-to-fire-event path
  documented in item 9;
* outbound notification email templates keyed by audit topic;
* a router that walks the reply-subject grammar
  ``[<jtbd>:<event>:<instance_id>]`` and dispatches to the FastAPI
  backend.

Operation source: this generator does **not** re-derive operations from
the bundle. It uses the same ``jtbd.url_segment`` + ``jtbd.transitions``
fields the OpenAPI generator already feeds into ``openapi.yaml`` so the
reply-subject grammar stays operationally pinned to the spec.

Shell scope: only the routing skeleton is generated. Hosts wire the
concrete IMAP / SMTP / SES / SendGrid bridge themselves. That
intentional cut is documented in the W3 task brief (item 9 of
``docs/improvements.md``).

Determinism: every emitted file is rendered from a jinja2 template
with sorted iteration over JTBDs and audit topics. Two regens of the
same bundle produce byte-identical output (Principle 1).
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"all_audit_topics",
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].label",
	"jtbds[].fields[].required",
	"jtbds[].id",
	"jtbds[].title",
	"jtbds[].transitions",
	"jtbds[].url_segment",
	"project.name",
	"project.package",
)


# Path of the canonical OpenAPI spec relative to the email package
# root. Hosts that move the spec must update this string in lockstep;
# the README references the same constant so the adapter and its docs
# never disagree.
_OPENAPI_REL_PATH = "../../openapi.yaml"


_ROOT_TEMPLATES: tuple[tuple[str, str], ...] = (
	("frontend_email/pyproject.toml.j2", "pyproject.toml"),
	("frontend_email/README.md.j2", "README.md"),
)


def _events_for_jtbd(jtbd: NormalizedJTBD) -> tuple[str, ...]:
	"""Sorted, deduplicated tuple of events the JTBD accepts."""

	out: set[str] = set()
	for tr in jtbd.transitions:
		event = tr.get("event")
		if isinstance(event, str) and event:
			out.add(event)
	return tuple(sorted(out))


def _route_view(jtbds: tuple[NormalizedJTBD, ...]) -> list[dict[str, object]]:
	"""Per-JTBD reply-subject route entries the templates iterate."""

	rows: list[dict[str, object]] = []
	for jt in sorted(jtbds, key=lambda j: j.id):
		fields = [
			{
				"id": f.id,
				"label": f.label,
				"required": f.required,
			}
			for f in sorted(jt.fields, key=lambda x: x.id)
		]
		for event in _events_for_jtbd(jt):
			rows.append(
				{
					"jtbd_id": jt.id,
					"jtbd_title": jt.title,
					"url_segment": jt.url_segment,
					"event": event,
					"fields": fields,
					# Subject grammar token — closed at generation time
					# so the regex in the router is deterministic across
					# bundles.
					"subject_token": f"{jt.id}:{event}",
				}
			)
	return rows


def _module_name(bundle: NormalizedBundle) -> str:
	return f"{bundle.project.package}_email"


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit the email-driven adapter shell as a per-bundle directory tree."""

	pkg = bundle.project.package
	root = f"frontend-email/{pkg}"
	module = _module_name(bundle)
	jtbds_sorted = tuple(sorted(bundle.jtbds, key=lambda j: j.id))
	routes = _route_view(jtbds_sorted)
	audit_topics = list(bundle.all_audit_topics)

	context: dict[str, object] = {
		"project": bundle.project,
		"bundle": bundle,
		"jtbds": jtbds_sorted,
		"routes": routes,
		"audit_topics": audit_topics,
		"module_name": module,
		"openapi_rel_path": _OPENAPI_REL_PATH,
	}

	files: list[GeneratedFile] = []
	for tpl, rel in _ROOT_TEMPLATES:
		files.append(
			GeneratedFile(
				path=f"{root}/{rel}",
				content=render(tpl, **context),
			)
		)
	src_root = f"{root}/src/{module}"
	files.append(
		GeneratedFile(
			path=f"{src_root}/__init__.py",
			content=render("frontend_email/src/__init__.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/inbound.py",
			content=render("frontend_email/src/inbound.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/templates.py",
			content=render("frontend_email/src/templates.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/router.py",
			content=render("frontend_email/src/router.py.j2", **context),
		)
	)
	return files
