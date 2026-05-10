"""Tests for the per-bundle frontend_slack generator (W3 / item 9).

Coverage:

* Generator emits the expected fixed set of files under
  ``frontend-slack/<package>/`` regardless of how many JTBDs the bundle
  declares (per-bundle aggregation, plan §1 principle 2).
* Slash command catalog mirrors JTBD/event combinations.
* Interactive-message templates exist for every audit topic the bundle
  aggregates.
* Generator output is byte-identical across two invocations against
  the same bundle (Principle 1).
* Slack adapter shell is invariant under the ``form_renderer`` flag.
* CONSUMES is mirrored in the fixture-registry primer.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import frontend_slack as gen
from flowforge_cli.jtbd.normalize import normalize


REPO_ROOT = Path(__file__).resolve().parents[3]
_INSURANCE_BUNDLE = REPO_ROOT / "examples" / "insurance_claim" / "jtbd-bundle.json"
_BUILDING_BUNDLE = REPO_ROOT / "examples" / "building-permit" / "jtbd-bundle.json"
_HIRING_BUNDLE = REPO_ROOT / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


EXPECTED_REL_PATHS_TEMPLATE: tuple[str, ...] = (
	"README.md",
	"pyproject.toml",
	"src/{module}/__init__.py",
	"src/{module}/commands.py",
	"src/{module}/messages.py",
	"src/{module}/router.py",
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def _expected_paths(module: str) -> tuple[str, ...]:
	return tuple(p.format(module=module) for p in EXPECTED_REL_PATHS_TEMPLATE)


def _slack_files(files: list[Any]) -> list[Any]:
	return [f for f in files if f.path.startswith("frontend-slack/")]


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_full_adapter_tree_under_package_dir() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	root = f"frontend-slack/{bundle.project.package}"
	module = f"{bundle.project.package}_slack"
	rel = sorted(f.path[len(root) + 1 :] for f in out)
	assert rel == sorted(_expected_paths(module))
	assert all(f.path.startswith(root + "/") for f in out)


def test_aggregates_one_adapter_per_bundle_not_per_jtbd() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	assert len(out) == len(EXPECTED_REL_PATHS_TEMPLATE)


def test_commands_lists_one_entry_per_jtbd_event() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	(commands_py,) = [f for f in out if f.path.endswith("/commands.py")]
	# Sanity: each (jtbd, event) pair shows up as one CommandSpec entry.
	for jt in bundle.jtbds:
		events = sorted({tr["event"] for tr in jt.transitions if tr.get("event")})
		for ev in events:
			assert f'jtbd_id="{jt.id}"' in commands_py.content
			assert f'event="{ev}"' in commands_py.content
	# Slash matches url_segment.
	for jt in bundle.jtbds:
		assert f'slash="{jt.url_segment}"' in commands_py.content


def test_commands_lookup_helper_present() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(commands_py,) = [f for f in out if f.path.endswith("/commands.py")]
	# Public lookup helper used by the router shell.
	assert "def lookup(slash: str, event: str)" in commands_py.content
	assert "SLASH_COMMANDS" in commands_py.content


def test_messages_template_per_audit_topic() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(messages_py,) = [f for f in out if f.path.endswith("/messages.py")]
	for topic in bundle.all_audit_topics:
		# Every audit topic gets a Block Kit payload entry.
		assert f'"{topic}":' in messages_py.content


def test_router_abstracts_signature_and_principal() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(router_py,) = [f for f in out if f.path.endswith("/router.py")]
	# Router is shell-only — host wires concrete bot.
	assert "class SlackAdapter(ABC)" in router_py.content
	assert "def verify_signature" in router_py.content
	assert "def resolve_principal" in router_py.content
	assert "async def post_event" in router_py.content
	assert "async def dispatch" in router_py.content


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
# Determinism
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
# Form-renderer flag invariance.
# ---------------------------------------------------------------------------


def _flip_form_renderer(raw: dict[str, Any], value: str) -> dict[str, Any]:
	clone = json.loads(json.dumps(raw))
	clone.setdefault("project", {}).setdefault("frontend", {})
	clone["project"]["frontend"]["form_renderer"] = value
	return clone


def test_slack_byte_identical_across_form_renderer_flag() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	skel = generate(_flip_form_renderer(raw, "skeleton"))
	real = generate(_flip_form_renderer(raw, "real"))
	skel_slack = {
		f.path: f.content for f in skel if f.path.startswith("frontend-slack/")
	}
	real_slack = {
		f.path: f.content for f in real if f.path.startswith("frontend-slack/")
	}
	assert skel_slack == real_slack


# ---------------------------------------------------------------------------
# Pipeline integration.
# ---------------------------------------------------------------------------


def test_pipeline_includes_frontend_slack_files() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	files = generate(raw)
	slack = _slack_files(files)
	module = f"{raw['project']['package']}_slack"
	rel = sorted(
		f.path[len(f"frontend-slack/{raw['project']['package']}/") :] for f in slack
	)
	assert rel == sorted(_expected_paths(module))


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("frontend_slack")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_frontend_slack() -> None:
	assert "frontend_slack" in _fixture_registry.all_generators()
