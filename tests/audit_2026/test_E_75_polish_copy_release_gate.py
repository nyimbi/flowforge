"""Ratchets for the fail-closed polish-copy release gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from flowforge_cli.jtbd.overrides import JtbdCopyOverrides


_ROOT = Path(__file__).resolve().parents[2]


def _load_gate_module() -> ModuleType:
	script = _ROOT / "scripts" / "audit_2026" / "check_polish_copy_sidecar.py"
	spec = importlib.util.spec_from_file_location("check_polish_copy_sidecar", script)
	assert spec is not None
	assert spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


_GATE = _load_gate_module()
_BUNDLE = _GATE._load_bundle(_ROOT / "examples" / "insurance_claim" / "jtbd-bundle.json")
_VALID_SIDE_CAR = {
	"tone_profile": "formal-professional",
	"strings": {
		"claim_intake.field.claimant_name.label": "Full legal name",
	},
	"llm_provider": "anthropic",
	"llm_model": "claude-test",
	"prompt_sha256": "a" * 64,
}


def test_external_release_runs_polish_copy_sidecar_gate() -> None:
	makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")
	assert ".PHONY: audit-2026-polish-copy-sidecar" in makefile
	assert "scripts/audit_2026/check_polish_copy_sidecar.py" in makefile
	release = makefile.split(".PHONY: audit-2026-release-external", 1)[1]
	assert "$(MAKE) audit-2026-polish-copy-sidecar" in release


def test_polish_copy_sidecar_gate_requires_llm_audit_metadata() -> None:
	script = (
		_ROOT / "scripts" / "audit_2026" / "check_polish_copy_sidecar.py"
	).read_text(encoding="utf-8")
	assert "examples/insurance_claim/jtbd-bundle.json" in script
	assert "llm_provider" in script
	assert "llm_model" in script
	assert "prompt_sha256" in script
	assert "validate_key_against_bundle" in script
	assert "FLOWFORGE_POLISH_PROVIDER=claude-cli" in script


def test_polish_copy_sidecar_authoring_workflow_uploads_review_candidate() -> None:
	workflow = (
		_ROOT / ".github" / "workflows" / "audit-2026-polish-copy-sidecar.yml"
	).read_text(encoding="utf-8")

	assert "workflow_dispatch:" in workflow
	assert "formal-professional" in workflow
	assert "friendly-direct" in workflow
	assert "regulator-compliant" in workflow
	assert "uv sync --all-packages --all-extras" in workflow
	assert 'uv run python -c "import anthropic' in workflow
	assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in workflow
	assert "CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}" in workflow
	assert "uv run flowforge polish-copy" in workflow
	assert "--require-llm" in workflow
	assert "--commit" in workflow
	assert "make audit-2026-polish-copy-sidecar" in workflow
	assert "git diff -- examples/insurance_claim/jtbd-bundle.json.overrides.json" in workflow
	assert "hashFiles('examples/insurance_claim/jtbd-bundle.json.overrides.json') != ''" in workflow
	assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4" in workflow
	assert "audit-2026-polish-copy-sidecar-candidate" in workflow


def test_polish_copy_sidecar_gate_accepts_reviewable_sidecar() -> None:
	sidecar = JtbdCopyOverrides.model_validate(_VALID_SIDE_CAR)
	assert _GATE._validate_sidecar(sidecar, _BUNDLE) is None


def test_polish_copy_sidecar_gate_rejects_empty_strings() -> None:
	payload = dict(_VALID_SIDE_CAR, strings={})
	sidecar = JtbdCopyOverrides.model_validate(payload)

	assert _GATE._validate_sidecar(sidecar, _BUNDLE) == (
		"sidecar has no strings; run a real LLM polish-copy authoring pass"
	)


def test_polish_copy_sidecar_gate_rejects_missing_llm_metadata() -> None:
	payload = dict(_VALID_SIDE_CAR, llm_model=None)
	sidecar = JtbdCopyOverrides.model_validate(payload)

	assert _GATE._validate_sidecar(sidecar, _BUNDLE) == (
		"sidecar missing LLM audit metadata: llm_model"
	)


def test_polish_copy_sidecar_gate_rejects_bad_prompt_hash() -> None:
	payload = dict(_VALID_SIDE_CAR, prompt_sha256="A" * 64)
	sidecar = JtbdCopyOverrides.model_validate(payload)

	assert _GATE._validate_sidecar(sidecar, _BUNDLE) == (
		"sidecar prompt_sha256 must be a lowercase 64-character hex digest"
	)


def test_polish_copy_sidecar_gate_rejects_dead_override_key() -> None:
	payload = dict(
		_VALID_SIDE_CAR,
		strings={
			"claim_intake.field.not_a_real_field.label": "Dead label",
		},
	)
	sidecar = JtbdCopyOverrides.model_validate(payload)

	err = _GATE._validate_sidecar(sidecar, _BUNDLE)
	assert err is not None
	assert "no data_capture field with id 'not_a_real_field'" in err
