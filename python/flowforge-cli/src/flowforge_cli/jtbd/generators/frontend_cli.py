"""Per-bundle generator: emit a Typer Python CLI client.

Item 9 of :doc:`docs/improvements`, W3 of
:doc:`docs/v0.3.0-engineering-plan`.

The CLI client is a standalone Python package distinct from
:mod:`.frontend` (Next.js customer surface), :mod:`.frontend_admin`
(operator console SPA), :mod:`.frontend_slack` (Slack adapter shell)
and :mod:`.frontend_email` (email-driven adapter shell). It mirrors
the operations declared by the W1 :mod:`.openapi` generator's
``openapi.yaml`` — one Typer subcommand per JTBD, one fire-event
command per derived workflow event, with one Typer ``--`` option per
``data_capture`` field — and POSTs payloads to ``/<url_segment>/events``
through an async :class:`httpx.AsyncClient` shim.

Why a separate package: the customer-facing webapp and the operator
console assume a browser; enterprise ops and customer-success teams
often need a scriptable ``flowforge-app`` interface for batch fixes,
debugging, and CI smoke tests. Keeping the CLI as a third generated
package means hosts ship it on its own release cadence and do not
drag in the React stack for headless deployments.

Operation source: this generator does **not** re-derive operations from
the bundle. It uses the same ``jtbd.url_segment`` + ``jtbd.transitions``
fields the OpenAPI generator already feeds into ``openapi.yaml`` so the
CLI's command tree stays operationally pinned to the spec. Hosts that
edit ``openapi.yaml`` by hand should rerun the generator to keep both
sides in lockstep.

Determinism: every emitted file is rendered from a jinja2 template with
sorted dict iteration over JTBDs, fields, and events. Two regens of the
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
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].kind",
	"jtbds[].fields[].label",
	"jtbds[].fields[].required",
	"jtbds[].id",
	"jtbds[].title",
	"jtbds[].transitions",
	"jtbds[].url_segment",
	"project.name",
	"project.package",
)


# Path of the canonical OpenAPI spec relative to the CLI package root.
# Hosts that move the spec must update this string in lockstep; the
# README references the same constant so the CLI and its docs never
# disagree.
_OPENAPI_REL_PATH = "../../openapi.yaml"


# Template files emitted at the CLI package's root. Paths are relative to
# ``frontend-cli/<package>/``. Each entry is ``(template, dest)``.
_ROOT_TEMPLATES: tuple[tuple[str, str], ...] = (
	("frontend_cli/pyproject.toml.j2", "pyproject.toml"),
	("frontend_cli/README.md.j2", "README.md"),
)


def _typer_field_option(kind: str) -> str:
	"""Map a ``data_capture`` field kind to a Typer option type annotation.

	Kept narrow: Typer covers ``str``, ``int``, ``float``, ``bool`` natively
	and we shed nothing by reducing every other kind to ``str`` (the JSON
	payload is the source of truth — type-coercion lives at the FastAPI
	router gate, not the CLI). The mapping here is deterministic so two
	regens emit identical option signatures.
	"""

	assert isinstance(kind, str), "kind must be a string"
	if kind in ("integer",):
		return "int"
	if kind in ("number", "money"):
		return "float"
	if kind in ("boolean",):
		return "bool"
	return "str"


def _events_for_jtbd(jtbd: NormalizedJTBD) -> tuple[str, ...]:
	"""Return the sorted, deduplicated tuple of events the JTBD accepts.

	Sourced from the synthesised transitions (which the OpenAPI generator's
	``example.event`` block also reads), so the CLI command tree stays in
	lockstep with the spec.
	"""

	out: set[str] = set()
	for tr in jtbd.transitions:
		event = tr.get("event")
		if isinstance(event, str) and event:
			out.add(event)
	return tuple(sorted(out))


def _command_view(jtbds: tuple[NormalizedJTBD, ...]) -> list[dict[str, object]]:
	"""Build the deterministic command tree the Typer template iterates.

	Returns one row per ``(jtbd, event)`` pair. Each row carries the JTBD
	identifiers + a sorted list of fields with their Typer option types.
	"""

	rows: list[dict[str, object]] = []
	for jt in sorted(jtbds, key=lambda j: j.id):
		fields = [
			{
				"id": f.id,
				"label": f.label,
				"required": f.required,
				"option_type": _typer_field_option(f.kind),
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
					# Function name is unique per (jtbd, event) so Typer's
					# command registry never collides.
					"func_name": f"{jt.id}_{event}",
					# CLI command name is the bare event token; the JTBD
					# subapp namespacing handles cross-JTBD disambiguation.
					"command_name": event.replace("_", "-"),
					"fields": fields,
				}
			)
	return rows


def _module_name(bundle: NormalizedBundle) -> str:
	"""Importable Python module name for the CLI package."""

	return f"{bundle.project.package}_cli"


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit the Typer CLI client as a per-bundle directory tree.

	All files land under ``frontend-cli/<project.package>/`` so two
	bundles can coexist in the same monorepo without colliding.
	"""

	pkg = bundle.project.package
	root = f"frontend-cli/{pkg}"
	module = _module_name(bundle)
	jtbds_sorted = tuple(sorted(bundle.jtbds, key=lambda j: j.id))
	commands = _command_view(jtbds_sorted)

	context: dict[str, object] = {
		"project": bundle.project,
		"bundle": bundle,
		"jtbds": jtbds_sorted,
		"commands": commands,
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
	# Python module files live under ``src/<module>/`` — the layout
	# matches the parent project's uv-workspace convention.
	src_root = f"{root}/src/{module}"
	files.append(
		GeneratedFile(
			path=f"{src_root}/__init__.py",
			content=render("frontend_cli/src/__init__.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/main.py",
			content=render("frontend_cli/src/main.py.j2", **context),
		)
	)
	files.append(
		GeneratedFile(
			path=f"{src_root}/client.py",
			content=render("frontend_cli/src/client.py.j2", **context),
		)
	)
	return files
