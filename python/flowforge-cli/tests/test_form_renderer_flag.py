"""Tests for v0.3.0 W1 / item 13: ``form_renderer`` flag emission paths.

Covers:

* The ``"skeleton"`` flag value (default) emits byte-identical output
  vs. the no-flag bundle — pre-W1 examples must regen unchanged.
* The ``"real"`` flag value flips Step.tsx.j2 onto the FormRenderer
  path — the legacy ``<dd>—</dd>`` placeholder is gone, the
  ``@flowforge/renderer`` import shows up.
* Both paths produce stable bytes across two invocations against the
  same bundle (deterministic regen).
* The cross-runtime fixture v2 loads cleanly and has the 50
  ``conditional``-tagged cases the ratchet expects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate


# Repo root sits 4 directories above this test file:
# .../flowforge/python/flowforge-cli/tests/test_form_renderer_flag.py
#   parents[0]=tests/, [1]=flowforge-cli/, [2]=python/, [3]=flowforge/ (repo root)
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_V2 = REPO_ROOT / "tests" / "cross_runtime" / "fixtures" / "expr_parity_v2.json"


def _bundle(form_renderer: str | None = None) -> dict[str, Any]:
	bundle: dict[str, Any] = {
		"project": {
			"name": "claims-demo",
			"package": "claims_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
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
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant",
						"required": True,
						"pii": True,
					},
					{
						"id": "loss_amount",
						"kind": "money",
						"label": "Loss",
						"required": True,
						"pii": False,
					},
				],
			}
		],
	}
	if form_renderer is not None:
		bundle["project"]["frontend"] = {"form_renderer": form_renderer}
	return bundle


def _step_tsx(files: list[Any]) -> str:
	(step,) = [f for f in files if f.path.endswith("ClaimIntakeStep.tsx")]
	return step.content


def test_default_flag_matches_skeleton_path() -> None:
	"""No frontend block → "skeleton" → byte-identical to explicit skeleton."""

	default = _step_tsx(generate(_bundle()))
	skeleton = _step_tsx(generate(_bundle("skeleton")))
	assert default == skeleton


def test_skeleton_path_emits_dd_placeholder() -> None:
	"""Skeleton path keeps the legacy `<dd>—</dd>` rendering intact."""

	tsx = _step_tsx(generate(_bundle("skeleton")))
	assert "<dd>—</dd>" in tsx, tsx
	assert "@flowforge/renderer" not in tsx, tsx


def test_real_path_emits_form_renderer_import() -> None:
	"""Real path wires `@flowforge/renderer`'s FormRenderer to form_spec.json."""

	tsx = _step_tsx(generate(_bundle("real")))
	assert "@flowforge/renderer" in tsx, tsx
	assert "FormRenderer" in tsx, tsx
	assert "form_spec.json" in tsx, tsx
	# PII visual treatment is wired (eye-toggle + masked default).
	assert "PII_FIELD_IDS" in tsx, tsx
	# aria-describedby links inline errors to their field ids.
	assert "aria-describedby" in tsx, tsx
	# Skeleton placeholder has been replaced — no `<dd>—</dd>` left over.
	assert "<dd>—</dd>" not in tsx, tsx


def test_both_paths_are_byte_deterministic() -> None:
	"""Two invocations against the same bundle return identical bytes."""

	for renderer in ("skeleton", "real"):
		a = _step_tsx(generate(_bundle(renderer)))
		b = _step_tsx(generate(_bundle(renderer)))
		assert a == b, f"non-deterministic regen for form_renderer={renderer!r}"


def test_real_path_balances_braces_and_parens() -> None:
	"""Cheap syntactic sanity check on the real path TSX."""

	tsx = _step_tsx(generate(_bundle("real")))
	assert tsx.count("{") == tsx.count("}"), tsx
	assert tsx.count("(") == tsx.count(")"), tsx


def test_fixture_v2_has_expected_shape() -> None:
	"""The cross-runtime parity fixture v2 lands with 250 cases including 50 conditional."""

	assert FIXTURE_V2.exists(), f"missing fixture v2 at {FIXTURE_V2}"
	data = json.loads(FIXTURE_V2.read_text())
	cases = data["cases"]
	assert len(cases) == 250, f"expected 250 cases, got {len(cases)}"

	tags = [c["tag"] for c in cases]
	conditional = [c for c in cases if c["tag"] == "conditional"]
	assert len(conditional) == 50, f"expected 50 conditional cases, got {len(conditional)}"
	# Every conditional case carries the show_if-shaped {var: ...} pattern
	# somewhere in its expression — sanity check that we're testing what
	# we say we're testing.
	for c in conditional:
		assert "var" in json.dumps(c["expr"]), c
	# IDs are unique across all 250 cases.
	ids = [c["id"] for c in cases]
	assert len(set(ids)) == len(ids), "duplicate ids"
	# Tag breadth includes both old and new tag classes.
	tag_set = set(tags)
	assert "conditional" in tag_set
	assert "==" in tag_set
	assert "var" in tag_set
