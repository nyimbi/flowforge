"""Per-bundle generator: emit a Slack adapter shell.

Item 9 of :doc:`docs/improvements`, W3 of
:doc:`docs/v0.3.0-engineering-plan`.

The Slack adapter is a standalone Python package distinct from
:mod:`.frontend` (Next.js customer surface), :mod:`.frontend_admin`
(operator console SPA), :mod:`.frontend_cli` (Typer CLI client) and
:mod:`.frontend_email` (email-driven adapter shell). It exposes:

* one slash command per JTBD (e.g. ``/claim-intake``) with a
  per-event subcommand grammar (``/claim-intake submit policy=ABC ...``);
* one interactive-message template per audit topic the bundle aggregates
  (button-action grammar following Slack's Block Kit convention).

Operation source: this generator does **not** re-derive operations from
the bundle. It uses the same ``jtbd.url_segment`` + ``jtbd.transitions``
fields the OpenAPI generator already feeds into ``openapi.yaml`` so the
slash-command catalog stays operationally pinned to the spec.

Shell scope: only the routing skeleton is generated. Hosts wire the
concrete Slack bot — webhook URL, signing secret, event delivery —
themselves. That intentional cut is documented in the W3 task brief
(item 9 of ``docs/improvements.md``).

Determinism: every emitted file is rendered from a jinja2 template with
sorted dict iteration over JTBDs and audit topics. Two regens of the
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
	"jtbds[].permissions",
	"jtbds[].title",
	"jtbds[].transitions",
	"jtbds[].url_segment",
	"project.name",
	"project.package",
)


# Path of the canonical OpenAPI spec relative to the Slack package root.
# Hosts that move the spec must update this string in lockstep; the
# README references the same constant so the adapter and its docs never
# disagree.
_OPENAPI_REL_PATH = "../../openapi.yaml"


_ROOT_TEMPLATES: tuple[tuple[str, str], ...] = (
	("frontend_slack/pyproject.toml.j2", "pyproject.toml"),
	("frontend_slack/README.md.j2", "README.md"),
)


def _events_for_jtbd(jtbd: NormalizedJTBD) -> tuple[str, ...]:
	"""Sorted, deduplicated tuple of events the JTBD accepts."""

	out: set[str] = set()
	for tr in jtbd.transitions:
		event = tr.get("event")
		if isinstance(event, str) and event:
			out.add(event)
	return tuple(sorted(out))


def _command_view(jtbds: tuple[NormalizedJTBD, ...]) -> list[dict[str, object]]:
	"""Build the per-JTBD slash-command catalog the templates iterate."""

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
		rows.append(
			{
				"jtbd_id": jt.id,
				"jtbd_title": jt.title,
				"url_segment": jt.url_segment,
				# Slack slash commands are conventionally lowercase
				# kebab-case; ``url_segment`` already satisfies that.
				"slash": jt.url_segment,
				"events": _events_for_jtbd(jt),
				"fields": fields,
				"permissions": list(jt.permissions),
			}
		)
	return rows


def _module_name(bundle: NormalizedBundle) -> str:
	return f"{bundle.project.package}_slack"


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit the Slack adapter shell as a per-bundle directory tree."""

	pkg = bundle.project.package
	root = f"frontend-slack/{pkg}"
	module = _module_name(bundle)
	jtbds_sorted = tuple(sorted(bundle.jtbds, key=lambda j: j.id))
	commands = _command_view(jtbds_sorted)
	audit_topics = list(bundle.all_audit_topics)

	context: dict[str, object] = {
		"project": bundle.project,
		"bundle": bundle,
		"jtbds": jtbds_sorted,
		"commands": commands,
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
			content=render("frontend_slack/src/__init__.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/commands.py",
			content=render("frontend_slack/src/commands.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/messages.py",
			content=render("frontend_slack/src/messages.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/router.py",
			content=render("frontend_slack/src/router.py.j2", **context),
		)
	)
	return files
