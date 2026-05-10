"""Tests for the per-bundle design-tokens generator (W3 item 18).

Covers:

* Six files emitted per bundle, at the documented customer + admin paths.
* Customer-facing and admin trees receive byte-identical token bodies
  (parity is the contract — a colour swap stays in lockstep).
* Default tokens kick in when ``project.design`` is omitted; declared
  tokens override only the keys the bundle author specifies.
* Output is byte-deterministic across two invocations on each example.
* Step.tsx real path imports ``design_tokens.css`` and references at
  least one CSS variable; skeleton path stays inert (no token wiring).
* Module-level CONSUMES matches the fixture-registry entry.
* Hex colour validator accepts ``#RGB``/``#RRGGBB``/``#RRGGBBAA`` and
  rejects malformed inputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import design_tokens as gen
from flowforge_cli.jtbd.normalize import DEFAULT_DESIGN, normalize


_REPO = Path(__file__).resolve().parents[3]
_INSURANCE_BUNDLE = _REPO / "examples" / "insurance_claim" / "jtbd-bundle.json"
_BUILDING_BUNDLE = _REPO / "examples" / "building-permit" / "jtbd-bundle.json"
_HIRING_BUNDLE = _REPO / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def _bundle(*, design: dict[str, Any] | None = None, form_renderer: str | None = None) -> dict[str, Any]:
	"""Compact synthetic bundle reused across the determinism + parity tests."""

	bundle: dict[str, Any] = {
		"project": {
			"name": "claims-demo",
			"package": "claims_demo",
			"domain": "claims",
			"tenancy": "single",
		},
		"shared": {
			"roles": ["adjuster"],
			"permissions": ["claim.read"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["queued within 24h"],
				"data_capture": [
					{"id": "claimant_name", "kind": "text", "label": "Claimant", "required": True, "pii": True},
				],
			}
		],
	}
	if design is not None:
		bundle["project"]["design"] = design
	if form_renderer is not None:
		bundle["project"].setdefault("frontend", {})["form_renderer"] = form_renderer
	return bundle


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_six_files_per_bundle() -> None:
	norm = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(norm)
	pkg = norm.project.package
	expected_paths = sorted(
		[
			f"frontend/src/{pkg}/design_tokens.css",
			f"frontend/{pkg}/tailwind.config.ts",
			f"frontend/src/{pkg}/theme.ts",
			f"frontend-admin/{pkg}/src/design_tokens.css",
			f"frontend-admin/{pkg}/tailwind.config.ts",
			f"frontend-admin/{pkg}/src/theme.ts",
		]
	)
	assert sorted(f.path for f in out) == expected_paths


def test_per_bundle_aggregation_one_set_for_multi_jtbd_bundle() -> None:
	"""5-JTBD building-permit bundle still emits exactly six files (per-bundle aggregation)."""

	norm = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(norm)
	assert len(out) == 6


# ---------------------------------------------------------------------------
# Customer ↔ admin parity
# ---------------------------------------------------------------------------


def test_customer_and_admin_token_bodies_are_identical() -> None:
	"""The same three artifacts must render byte-identically into both trees."""

	norm = _load_normalized(_INSURANCE_BUNDLE)
	files = {f.path: f.content for f in gen.generate(norm)}
	pkg = norm.project.package
	pairs = [
		(f"frontend/src/{pkg}/design_tokens.css", f"frontend-admin/{pkg}/src/design_tokens.css"),
		(f"frontend/{pkg}/tailwind.config.ts", f"frontend-admin/{pkg}/tailwind.config.ts"),
		(f"frontend/src/{pkg}/theme.ts", f"frontend-admin/{pkg}/src/theme.ts"),
	]
	for customer_path, admin_path in pairs:
		assert files[customer_path] == files[admin_path], (
			f"design-token parity broken: {customer_path} differs from {admin_path}"
		)


# ---------------------------------------------------------------------------
# Default tokens vs explicit overrides
# ---------------------------------------------------------------------------


def test_missing_design_block_uses_defaults() -> None:
	"""A bundle with no ``project.design`` block emits the canonical defaults."""

	norm = normalize(_bundle())
	files = {f.path: f.content for f in gen.generate(norm)}
	css = files["frontend/src/claims_demo/design_tokens.css"]
	assert f"--color-primary: {DEFAULT_DESIGN.primary};" in css, css
	assert f"--color-accent: {DEFAULT_DESIGN.accent};" in css, css
	assert f"--font-family: {DEFAULT_DESIGN.font_family};" in css, css
	assert "--density: comfortable;" in css, css


def test_declared_design_block_overrides_defaults() -> None:
	"""Tokens declared on the bundle override the corresponding defaults."""

	norm = normalize(
		_bundle(
			design={
				"primary": "#0F766E",  # uppercase hex → normalized to lowercase
				"accent": "#f59e0b",
				"font_family": "\"IBM Plex Sans\", system-ui, sans-serif",
				"density": "compact",
				"radius_scale": 1.5,
			}
		)
	)
	files = {f.path: f.content for f in gen.generate(norm)}
	css = files["frontend/src/claims_demo/design_tokens.css"]
	assert "--color-primary: #0f766e;" in css, css
	assert "--color-accent: #f59e0b;" in css, css
	assert "--density: compact;" in css, css
	assert "--density-padding: 0.5rem;" in css, css
	assert "--radius-md: 12px;" in css, css


def test_partial_design_block_preserves_default_keys() -> None:
	"""Only the keys the author overrides change; the rest carry defaults."""

	norm = normalize(_bundle(design={"primary": "#abc"}))
	css = next(
		f.content
		for f in gen.generate(norm)
		if f.path == "frontend/src/claims_demo/design_tokens.css"
	)
	# Override took effect.
	assert "--color-primary: #abc;" in css
	# Defaults for the other tokens preserved.
	assert f"--color-accent: {DEFAULT_DESIGN.accent};" in css
	assert "--density: comfortable;" in css


# ---------------------------------------------------------------------------
# Determinism (Principle 1 + plan §6 cumulative gate)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bundle_path", [_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE])
def test_deterministic_output(bundle_path: Path) -> None:
	norm = _load_normalized(bundle_path)
	first = gen.generate(norm)
	second = gen.generate(norm)
	assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


@pytest.mark.parametrize("flag", ["skeleton", "real"])
@pytest.mark.parametrize("bundle_path", [_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE])
def test_pipeline_deterministic_across_form_renderer_flag(
	bundle_path: Path, flag: str
) -> None:
	"""End-to-end pipeline is deterministic across both form_renderer values."""

	raw = json.loads(bundle_path.read_text(encoding="utf-8"))
	raw.setdefault("project", {}).setdefault("frontend", {})["form_renderer"] = flag
	first = generate(raw)
	second = generate(raw)
	assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


# ---------------------------------------------------------------------------
# Step.tsx wiring: real path imports tokens, skeleton path stays inert
# ---------------------------------------------------------------------------


def _step_tsx(files: list[Any]) -> str:
	(step,) = [f for f in files if f.path.endswith("ClaimIntakeStep.tsx")]
	return step.content


def test_real_path_imports_design_tokens_css() -> None:
	tsx = _step_tsx(generate(_bundle(form_renderer="real")))
	assert 'import "../../claims_demo/design_tokens.css"' in tsx, tsx


def test_real_path_references_css_variables() -> None:
	tsx = _step_tsx(generate(_bundle(form_renderer="real")))
	# At least the primary colour, font family, and a radius variable.
	assert "var(--color-primary)" in tsx, tsx
	assert "var(--font-family)" in tsx, tsx
	assert "var(--radius-md)" in tsx, tsx


def test_skeleton_path_stays_token_free() -> None:
	"""Skeleton path stays unchanged — no token import, no var() refs."""

	tsx = _step_tsx(generate(_bundle(form_renderer="skeleton")))
	assert "design_tokens.css" not in tsx, tsx
	assert "var(--color-primary)" not in tsx, tsx


# ---------------------------------------------------------------------------
# Admin tree wiring
# ---------------------------------------------------------------------------


def test_admin_main_imports_design_tokens_css() -> None:
	"""Admin main.tsx imports design_tokens.css for theme parity."""

	files = generate(_bundle())
	(main,) = [f for f in files if f.path.endswith("frontend-admin/claims_demo/src/main.tsx")]
	assert 'import "./design_tokens.css"' in main.content, main.content


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_pipeline_emits_design_token_files_for_every_example() -> None:
	"""End-to-end: ``flowforge_cli.jtbd.generate`` includes the six token files."""

	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		files = generate(raw)
		paths = {f.path for f in files}
		pkg = raw["project"]["package"]
		expected = {
			f"frontend/src/{pkg}/design_tokens.css",
			f"frontend/{pkg}/tailwind.config.ts",
			f"frontend/src/{pkg}/theme.ts",
			f"frontend-admin/{pkg}/src/design_tokens.css",
			f"frontend-admin/{pkg}/tailwind.config.ts",
			f"frontend-admin/{pkg}/src/theme.ts",
		}
		missing = expected - paths
		assert not missing, f"{path.name}: pipeline missing token files {sorted(missing)}"


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("design_tokens")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_design_tokens() -> None:
	assert "design_tokens" in _fixture_registry.all_generators()


# ---------------------------------------------------------------------------
# JtbdDesign hex validator
# ---------------------------------------------------------------------------


def test_hex_validator_accepts_three_six_eight_digit_hex() -> None:
	from flowforge_jtbd.dsl.spec import JtbdDesign

	for value in ["#abc", "#ABC", "#0f766e", "#0F766E", "#0f766eFF"]:
		d = JtbdDesign(primary=value, accent="#10b981")
		assert d.primary.startswith("#")
		assert d.primary == value.lower()


def test_hex_validator_rejects_malformed_inputs() -> None:
	from pydantic import ValidationError

	from flowforge_jtbd.dsl.spec import JtbdDesign

	for value in ["", "abc", "#", "#xyz", "#1234", "#1234567"]:
		with pytest.raises(ValidationError):
			JtbdDesign(primary=value)


def test_design_density_enum_rejects_unknown() -> None:
	from pydantic import ValidationError

	from flowforge_jtbd.dsl.spec import JtbdDesign

	with pytest.raises(ValidationError):
		JtbdDesign(density="cozy")  # type: ignore[arg-type]


def test_radius_scale_bounds() -> None:
	from pydantic import ValidationError

	from flowforge_jtbd.dsl.spec import JtbdDesign

	# Lower bound ≥ 0.0, upper bound ≤ 4.0.
	JtbdDesign(radius_scale=0.0)
	JtbdDesign(radius_scale=4.0)
	with pytest.raises(ValidationError):
		JtbdDesign(radius_scale=-0.1)
	with pytest.raises(ValidationError):
		JtbdDesign(radius_scale=4.1)
