"""``flowforge new <project> --jtbd <bundle>`` — backend-skeleton scaffolder.

Loads a JTBD bundle, validates it against the bundled JSON schema, then
renders a deterministic backend project skeleton from Jinja2 templates.
"""

from __future__ import annotations

import json
from importlib.resources import files as _ir_files
from pathlib import Path
from typing import Any

import typer
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jsonschema import Draft202012Validator

from .._io import load_structured, write_json


def register(app: typer.Typer) -> None:
	app.command("new", help="Scaffold a project from a JTBD bundle.")(new_cmd)


def new_cmd(
	project: str = typer.Argument(..., help="Project directory to create."),
	jtbd: Path = typer.Option(..., "--jtbd", exists=True, dir_okay=False, help="JTBD bundle file."),
	out: Path | None = typer.Option(None, "--out", help="Parent directory (default: current working directory)."),
	force: bool = typer.Option(False, "--force", help="Allow scaffolding into a non-empty directory."),
) -> None:
	"""Scaffold the backend skeleton for *project* from *jtbd*."""

	assert project, "project name is required"
	assert jtbd is not None

	parent = (out or Path.cwd()).resolve()
	target = parent / project
	if target.exists() and any(target.iterdir()) and not force:
		raise typer.BadParameter(f"target {target} exists and is not empty (use --force).")
	target.mkdir(parents=True, exist_ok=True)

	bundle = load_structured(jtbd)
	_validate_bundle(bundle)

	pkg_name = bundle["project"]["package"]
	jtbds = bundle.get("jtbds", [])

	typer.echo("flowforge — scaffolder")
	typer.echo("")
	typer.echo("[1/4] Validating JTBD bundle")
	typer.echo(
		f"      ✓ schema valid ({len(jtbds)} JTBD{'s' if len(jtbds) != 1 else ''}, "
		f"package={pkg_name})"
	)

	typer.echo("[2/4] Rendering backend skeleton")
	rendered = _render_backend(target, bundle)
	for rel in rendered:
		typer.echo(f"      created  {rel}")

	typer.echo("[3/4] Writing workflow stubs")
	wf_files = _write_workflow_stubs(target, bundle)
	for rel in wf_files:
		typer.echo(f"      created  {rel}")

	typer.echo("[4/4] Writing JTBD bundle copy")
	bundle_dst = target / "workflows" / "jtbd_bundle.json"
	write_json(bundle_dst, bundle)
	typer.echo(f"      created  {bundle_dst.relative_to(target)}")

	typer.echo("")
	typer.echo(f"generated project at {target}")


# -- helpers ---------------------------------------------------------------

_JTBD_SCHEMA: dict[str, Any] | None = None


def _jtbd_schema() -> dict[str, Any]:
	global _JTBD_SCHEMA
	if _JTBD_SCHEMA is not None:
		return _JTBD_SCHEMA
	try:
		res = _ir_files("flowforge.dsl.schema").joinpath("jtbd-1.0.schema.json")
		schema = json.loads(res.read_text())
	except Exception:
		# editable-install fallback
		import flowforge as _ff

		assert _ff.__file__ is not None
		ff_path = Path(_ff.__file__).resolve().parent
		candidate = ff_path / "dsl" / "schema" / "jtbd-1.0.schema.json"
		schema = json.loads(candidate.read_text())
	assert isinstance(schema, dict)
	_JTBD_SCHEMA = schema
	return schema


def _validate_bundle(bundle: dict[str, Any]) -> None:
	validator = Draft202012Validator(_jtbd_schema())
	errs = sorted(validator.iter_errors(bundle), key=lambda e: list(e.absolute_path))
	if errs:
		paths = "; ".join(
			f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errs[:5]
		)
		raise typer.BadParameter(f"JTBD bundle invalid: {paths}")


def _jinja_env() -> Environment:
	tpl_root = Path(__file__).resolve().parent.parent / "templates"
	return Environment(
		loader=FileSystemLoader(str(tpl_root)),
		autoescape=False,
		keep_trailing_newline=True,
		undefined=StrictUndefined,
	)


def _render_backend(target: Path, bundle: dict[str, Any]) -> list[str]:
	env = _jinja_env()
	pkg = bundle["project"]["package"]

	plan: list[tuple[str, str]] = [
		("backend/pyproject.toml.j2", "backend/pyproject.toml"),
		("backend/README.md.j2", "backend/README.md"),
		("backend/src/__pkg__/__init__.py.j2", f"backend/src/{pkg}/__init__.py"),
		("backend/src/__pkg__/main.py.j2", f"backend/src/{pkg}/main.py"),
		("backend/src/__pkg__/config.py.j2", f"backend/src/{pkg}/config.py"),
		("backend/src/__pkg__/workflow_adapter.py.j2", f"backend/src/{pkg}/workflow_adapter.py"),
		("backend/tests/__init__.py.j2", "backend/tests/__init__.py"),
		("backend/tests/test_workflow_adapter.py.j2", "backend/tests/test_workflow_adapter.py"),
		(".env.example.j2", ".env.example"),
		("README.md.j2", "README.md"),
	]
	created: list[str] = []
	for tpl, rel in plan:
		text = env.get_template(tpl).render(
			project=bundle["project"],
			jtbds=bundle.get("jtbds", []),
			shared=bundle.get("shared", {}),
		)
		dst = target / rel
		dst.parent.mkdir(parents=True, exist_ok=True)
		dst.write_text(text, encoding="utf-8")
		created.append(rel)
	return created


def _write_workflow_stubs(target: Path, bundle: dict[str, Any]) -> list[str]:
	"""Emit one stub workflow definition per JTBD (deterministic, schema-valid)."""

	created: list[str] = []
	for jtbd in bundle.get("jtbds", []):
		jt_id = jtbd["id"]
		wf = _stub_workflow_for_jtbd(jtbd, bundle["project"]["domain"])
		rel = Path("workflows") / jt_id / "definition.json"
		write_json(target / rel, wf)
		created.append(str(rel))
	return created


def _stub_workflow_for_jtbd(jtbd: dict[str, Any], subject_kind: str) -> dict[str, Any]:
	"""Return a 3-state DSL stub: intake → review → done."""

	jt_id = jtbd["id"]
	return {
		"key": jt_id,
		"version": "0.1.0",
		"subject_kind": subject_kind,
		"initial_state": "intake",
		"metadata": {"generated_from": "jtbd"},
		"states": [
			{"name": "intake", "kind": "manual_review", "swimlane": "applicant"},
			{"name": "review", "kind": "manual_review", "swimlane": "reviewer"},
			{"name": "done", "kind": "terminal_success"},
		],
		"transitions": [
			{
				"id": f"{jt_id}_submit",
				"event": "submit",
				"from_state": "intake",
				"to_state": "review",
				"priority": 0,
				"guards": [],
				"gates": [],
				"effects": [],
			},
			{
				"id": f"{jt_id}_approve",
				"event": "approve",
				"from_state": "review",
				"to_state": "done",
				"priority": 0,
				"guards": [],
				"gates": [],
				"effects": [],
			},
		],
	}
