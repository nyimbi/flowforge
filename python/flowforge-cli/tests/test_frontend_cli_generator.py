"""Tests for the per-bundle frontend_cli generator (W3 / item 9).

Coverage:

* Generator emits the expected fixed set of files under
  ``frontend-cli/<package>/`` regardless of how many JTBDs the bundle
  declares (per-bundle aggregation, plan §1 principle 2).
* Command tree mirrors the OpenAPI operations (one Typer subapp per
  JTBD, one command per derived event).
* Field options match the JTBD's data_capture shape — type annotations
  match the kind, required flags are honoured.
* Generator output is byte-identical across two invocations against
  the same bundle (Principle 1).
* CLI is invariant under the ``form_renderer`` flag — flipping
  ``project.frontend.form_renderer`` between ``"skeleton"`` and
  ``"real"`` does not change a single byte under ``frontend-cli/``.
* CONSUMES is mirrored in the fixture-registry primer.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import frontend_cli as gen
from flowforge_cli.jtbd.normalize import normalize


REPO_ROOT = Path(__file__).resolve().parents[3]
_INSURANCE_BUNDLE = REPO_ROOT / "examples" / "insurance_claim" / "jtbd-bundle.json"
_BUILDING_BUNDLE = REPO_ROOT / "examples" / "building-permit" / "jtbd-bundle.json"
_HIRING_BUNDLE = REPO_ROOT / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


# Files every CLI app must include — keyed off the canonical layout
# the generator advertises. The Python module name carries a ``_cli``
# suffix to disambiguate from the backend package when both are
# installed in the same environment.
EXPECTED_REL_PATHS_TEMPLATE: tuple[str, ...] = (
	"README.md",
	"pyproject.toml",
	"src/{module}/__init__.py",
	"src/{module}/client.py",
	"src/{module}/main.py",
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def _expected_paths(module: str) -> tuple[str, ...]:
	return tuple(p.format(module=module) for p in EXPECTED_REL_PATHS_TEMPLATE)


def _cli_files(files: list[Any]) -> list[Any]:
	return [f for f in files if f.path.startswith("frontend-cli/")]


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_full_cli_tree_under_package_dir() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	root = f"frontend-cli/{bundle.project.package}"
	module = f"{bundle.project.package}_cli"
	rel = sorted(f.path[len(root) + 1 :] for f in out)
	assert rel == sorted(_expected_paths(module))
	assert all(f.path.startswith(root + "/") for f in out)


def test_aggregates_one_app_per_bundle_not_per_jtbd() -> None:
	# building-permit has 5 JTBDs; the CLI is still a single tree.
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	assert len(out) == len(EXPECTED_REL_PATHS_TEMPLATE)


def test_pyproject_declares_typer_and_httpx_deps() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(pyproject,) = [f for f in out if f.path.endswith("/pyproject.toml")]
	# Both runtime deps the CLI relies on.
	assert "typer>=" in pyproject.content
	assert "httpx>=" in pyproject.content
	# Console script entry point — kebab-cased package name.
	assert "insurance-claim-demo-cli =" in pyproject.content


def test_main_py_subapp_per_jtbd() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	(main_py,) = [f for f in out if f.path.endswith("/main.py")]
	# Each JTBD lands as its own Typer subapp registered with
	# ``app.add_typer``.
	for jt in bundle.jtbds:
		assert f"{jt.id}_app = typer.Typer(" in main_py.content
		assert f'app.add_typer({jt.id}_app, name="{jt.url_segment}")' in main_py.content


def test_main_py_command_per_jtbd_event() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(main_py,) = [f for f in out if f.path.endswith("/main.py")]
	(jt,) = bundle.jtbds
	events = sorted({tr["event"] for tr in jt.transitions if tr.get("event")})
	for ev in events:
		# Each (jtbd, event) pair gets a unique Typer command.
		decorator = f'@{jt.id}_app.command("{ev.replace("_", "-")}")'
		func = f"def {jt.id}_{ev}("
		assert decorator in main_py.content
		assert func in main_py.content


def test_main_py_required_field_options() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(main_py,) = [f for f in out if f.path.endswith("/main.py")]
	(jt,) = bundle.jtbds
	for f in jt.fields:
		if f.required:
			assert f"{f.id}:" in main_py.content
			# Required options carry typer.Option(...).
			assert f'{f.id}: ' in main_py.content
	# A required string field's help text carries the (required) tag.
	assert "(required)" in main_py.content


def test_main_py_field_kind_to_option_type() -> None:
	"""data_capture kind → typer option type annotation."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(main_py,) = [f for f in out if f.path.endswith("/main.py")]
	# loss_amount is money → float
	assert "loss_amount: float" in main_py.content
	# contact_email is email → str
	assert "contact_email: str" in main_py.content
	# Optional fields land as Optional[X].
	assert "Optional[str] = typer.Option(None" in main_py.content


def test_client_py_async_httpx_wrapper() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(client_py,) = [f for f in out if f.path.endswith("/client.py")]
	assert "httpx.AsyncClient" in client_py.content
	assert "class FlowForgeClient" in client_py.content
	assert "async def fire(" in client_py.content
	# Sync helper exists for the Typer command bodies.
	assert "def fire_sync(" in client_py.content


def test_readme_references_openapi_path() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(readme,) = [f for f in out if f.path.endswith("/README.md")]
	# Uses the W1 OpenAPI spec, not re-derived operations.
	assert "openapi.yaml" in readme.content
	assert "../../openapi.yaml" in readme.content


# ---------------------------------------------------------------------------
# Generated python is syntactically valid
# ---------------------------------------------------------------------------


def test_generated_python_files_parse_cleanly() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	for f in out:
		if f.path.endswith(".py"):
			ast.parse(f.content)


def test_generated_python_files_parse_cleanly_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	for f in out:
		if f.path.endswith(".py"):
			ast.parse(f.content)


# ---------------------------------------------------------------------------
# Determinism (Principle 1 + plan §6 cumulative gate)
# ---------------------------------------------------------------------------


def test_deterministic_output_insurance_claim() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert [(f.path, f.content) for f in first] == [
		(f.path, f.content) for f in second
	]


def test_deterministic_output_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert [(f.path, f.content) for f in first] == [
		(f.path, f.content) for f in second
	]


def test_deterministic_output_hiring_pipeline() -> None:
	bundle = _load_normalized(_HIRING_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert [(f.path, f.content) for f in first] == [
		(f.path, f.content) for f in second
	]


# ---------------------------------------------------------------------------
# Form-renderer flag invariance — CLI must not depend on it.
# ---------------------------------------------------------------------------


def _flip_form_renderer(raw: dict[str, Any], value: str) -> dict[str, Any]:
	clone = json.loads(json.dumps(raw))
	clone.setdefault("project", {}).setdefault("frontend", {})
	clone["project"]["frontend"]["form_renderer"] = value
	return clone


def test_cli_byte_identical_across_form_renderer_flag() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	skel = generate(_flip_form_renderer(raw, "skeleton"))
	real = generate(_flip_form_renderer(raw, "real"))
	skel_cli = {f.path: f.content for f in skel if f.path.startswith("frontend-cli/")}
	real_cli = {f.path: f.content for f in real if f.path.startswith("frontend-cli/")}
	assert skel_cli == real_cli


# ---------------------------------------------------------------------------
# Pipeline integration — generator wired through ``generate``.
# ---------------------------------------------------------------------------


def test_pipeline_includes_frontend_cli_files() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	files = generate(raw)
	cli = _cli_files(files)
	module = f"{raw['project']['package']}_cli"
	rel = sorted(
		f.path[len(f"frontend-cli/{raw['project']['package']}/") :] for f in cli
	)
	assert rel == sorted(_expected_paths(module))


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("frontend_cli")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_frontend_cli() -> None:
	assert "frontend_cli" in _fixture_registry.all_generators()
