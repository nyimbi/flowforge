"""Tests for the per-bundle frontend_email generator (W3 / item 9).

Coverage:

* Generator emits the expected fixed set of files under
  ``frontend-email/<package>/`` regardless of how many JTBDs the bundle
  declares (per-bundle aggregation, plan §1 principle 2).
* Reply-subject route catalog mirrors JTBD/event combinations.
* Outbound email templates exist for every audit topic the bundle
  aggregates.
* Generator output is byte-identical across two invocations against
  the same bundle (Principle 1).
* Email adapter shell is invariant under the ``form_renderer`` flag.
* CONSUMES is mirrored in the fixture-registry primer.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import frontend_email as gen
from flowforge_cli.jtbd.normalize import normalize


REPO_ROOT = Path(__file__).resolve().parents[3]
_INSURANCE_BUNDLE = REPO_ROOT / "examples" / "insurance_claim" / "jtbd-bundle.json"
_BUILDING_BUNDLE = REPO_ROOT / "examples" / "building-permit" / "jtbd-bundle.json"
_HIRING_BUNDLE = REPO_ROOT / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


EXPECTED_REL_PATHS_TEMPLATE: tuple[str, ...] = (
	"README.md",
	"pyproject.toml",
	"src/{module}/__init__.py",
	"src/{module}/inbound.py",
	"src/{module}/router.py",
	"src/{module}/templates.py",
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def _expected_paths(module: str) -> tuple[str, ...]:
	return tuple(p.format(module=module) for p in EXPECTED_REL_PATHS_TEMPLATE)


def _email_files(files: list[Any]) -> list[Any]:
	return [f for f in files if f.path.startswith("frontend-email/")]


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_full_adapter_tree_under_package_dir() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	root = f"frontend-email/{bundle.project.package}"
	module = f"{bundle.project.package}_email"
	rel = sorted(f.path[len(root) + 1 :] for f in out)
	assert rel == sorted(_expected_paths(module))
	assert all(f.path.startswith(root + "/") for f in out)


def test_aggregates_one_adapter_per_bundle_not_per_jtbd() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	assert len(out) == len(EXPECTED_REL_PATHS_TEMPLATE)


def test_inbound_lists_one_route_per_jtbd_event() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	(inbound_py,) = [f for f in out if f.path.endswith("/inbound.py")]
	for jt in bundle.jtbds:
		events = sorted({tr["event"] for tr in jt.transitions if tr.get("event")})
		for ev in events:
			assert f'jtbd_id="{jt.id}"' in inbound_py.content
			assert f'subject_token="{jt.id}:{ev}"' in inbound_py.content


def test_inbound_carries_subject_grammar_regex() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(inbound_py,) = [f for f in out if f.path.endswith("/inbound.py")]
	# Subject regex is the closed grammar declared in the README.
	assert "_SUBJECT_RE" in inbound_py.content
	assert "def parse_subject(" in inbound_py.content
	assert "def parse_body(" in inbound_py.content
	assert "def lookup(" in inbound_py.content


def test_templates_one_email_per_audit_topic() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(templates_py,) = [f for f in out if f.path.endswith("/templates.py")]
	for topic in bundle.all_audit_topics:
		# Every audit topic gets an email template entry.
		assert f'"{topic}":' in templates_py.content


def test_router_abstracts_envelope_and_principal() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(router_py,) = [f for f in out if f.path.endswith("/router.py")]
	# Router is shell-only — host wires concrete IMAP/SMTP transport.
	assert "class EmailAdapter(ABC)" in router_py.content
	assert "def verify_envelope" in router_py.content
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


def test_email_byte_identical_across_form_renderer_flag() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	skel = generate(_flip_form_renderer(raw, "skeleton"))
	real = generate(_flip_form_renderer(raw, "real"))
	skel_email = {
		f.path: f.content for f in skel if f.path.startswith("frontend-email/")
	}
	real_email = {
		f.path: f.content for f in real if f.path.startswith("frontend-email/")
	}
	assert skel_email == real_email


# ---------------------------------------------------------------------------
# Pipeline integration.
# ---------------------------------------------------------------------------


def test_pipeline_includes_frontend_email_files() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	files = generate(raw)
	email = _email_files(files)
	module = f"{raw['project']['package']}_email"
	rel = sorted(
		f.path[len(f"frontend-email/{raw['project']['package']}/") :] for f in email
	)
	assert rel == sorted(_expected_paths(module))


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("frontend_email")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_frontend_email() -> None:
	assert "frontend_email" in _fixture_registry.all_generators()
