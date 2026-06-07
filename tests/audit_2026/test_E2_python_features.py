"""v0.4.0 E2 Python engineering acceptance tests.

Tests:
  - compliance-lint exits 0 on the insurance example bundle.
  - quality-score exits 0 with JSON output on the insurance bundle.
  - jtbd-precommit.sh is executable.
  - jtbd-lint.yml is valid YAML.
  - ai-draft fails closed (exit 1) when ANTHROPIC_API_KEY is not set.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSURANCE_BUNDLE = _REPO_ROOT / "examples" / "insurance_claim" / "jtbd-bundle.json"
_PRECOMMIT_HOOK = _REPO_ROOT / "scripts" / "ci" / "jtbd-precommit.sh"
_JTBD_LINT_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "jtbd-lint.yml"

# Use the same Python executable that is running the tests so the
# installed flowforge CLI is always reachable via ``-m flowforge_cli``.
_PYTHON = sys.executable


def _run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
	"""Run flowforge CLI via ``python -m flowforge_cli.main`` and return the result."""
	cmd = [_PYTHON, "-m", "flowforge_cli.main", *args]
	return subprocess.run(
		cmd,
		capture_output=True,
		text=True,
		env=env,
	)


# ---------------------------------------------------------------------------
# compliance-lint on insurance bundle
# ---------------------------------------------------------------------------


def test_compliance_lint_exits_0_on_insurance_bundle() -> None:
	"""compliance-lint must exit 0 on the canonical insurance example bundle."""
	assert _INSURANCE_BUNDLE.exists(), f"fixture not found: {_INSURANCE_BUNDLE}"
	result = _run_cli("jtbd", "compliance-lint", str(_INSURANCE_BUNDLE))
	assert result.returncode == 0, (
		f"compliance-lint exited {result.returncode}\n"
		f"stdout: {result.stdout}\n"
		f"stderr: {result.stderr}"
	)


def test_compliance_lint_json_output() -> None:
	"""compliance-lint --format json must emit valid JSON with ok/bundle_id keys."""
	assert _INSURANCE_BUNDLE.exists(), f"fixture not found: {_INSURANCE_BUNDLE}"
	result = _run_cli("jtbd", "compliance-lint", str(_INSURANCE_BUNDLE), "--format", "json")
	assert result.returncode == 0, (
		f"compliance-lint --format json exited {result.returncode}\n"
		f"stdout: {result.stdout}\nstderr: {result.stderr}"
	)
	data = json.loads(result.stdout)
	assert "ok" in data
	assert "bundle_id" in data


# ---------------------------------------------------------------------------
# quality-score on insurance bundle
# ---------------------------------------------------------------------------


def test_quality_score_exits_0_on_insurance_bundle() -> None:
	"""quality-score must exit 0 on the canonical insurance bundle."""
	assert _INSURANCE_BUNDLE.exists(), f"fixture not found: {_INSURANCE_BUNDLE}"
	result = _run_cli("jtbd", "quality-score", str(_INSURANCE_BUNDLE))
	assert result.returncode == 0, (
		f"quality-score exited {result.returncode}\n"
		f"stdout: {result.stdout}\nstderr: {result.stderr}"
	)


def test_quality_score_json_output() -> None:
	"""quality-score --json must emit valid JSON with expected structure."""
	assert _INSURANCE_BUNDLE.exists(), f"fixture not found: {_INSURANCE_BUNDLE}"
	result = _run_cli("jtbd", "quality-score", str(_INSURANCE_BUNDLE), "--json")
	assert result.returncode == 0, (
		f"quality-score --json exited {result.returncode}\n"
		f"stdout: {result.stdout}\nstderr: {result.stderr}"
	)
	data = json.loads(result.stdout)
	assert "bundle" in data
	assert "jtbds" in data
	assert isinstance(data["jtbds"], list)
	assert len(data["jtbds"]) > 0
	first = data["jtbds"][0]
	assert "id" in first
	assert "score" in first
	assert "dimensions" in first
	assert isinstance(first["score"], int)
	assert 0 <= first["score"] <= 100


# ---------------------------------------------------------------------------
# pre-commit hook is executable
# ---------------------------------------------------------------------------


def test_precommit_hook_is_executable() -> None:
	"""scripts/ci/jtbd-precommit.sh must exist and have execute permission."""
	assert _PRECOMMIT_HOOK.exists(), f"precommit hook not found: {_PRECOMMIT_HOOK}"
	mode = _PRECOMMIT_HOOK.stat().st_mode
	assert mode & stat.S_IXUSR, (
		f"{_PRECOMMIT_HOOK} is not user-executable (mode {oct(mode)})"
	)


def test_precommit_hook_has_shebang() -> None:
	"""jtbd-precommit.sh must have a bash shebang line."""
	first_line = _PRECOMMIT_HOOK.read_text(encoding="utf-8").splitlines()[0]
	assert first_line.startswith("#!"), f"Missing shebang: {first_line!r}"
	assert "bash" in first_line or "sh" in first_line, (
		f"Shebang doesn't reference a shell: {first_line!r}"
	)


# ---------------------------------------------------------------------------
# jtbd-lint.yml is valid YAML
# ---------------------------------------------------------------------------


def test_jtbd_lint_workflow_is_valid_yaml() -> None:
	"""jtbd-lint.yml must exist and parse as valid YAML."""
	assert _JTBD_LINT_WORKFLOW.exists(), f"workflow not found: {_JTBD_LINT_WORKFLOW}"
	content = _JTBD_LINT_WORKFLOW.read_text(encoding="utf-8")
	doc = yaml.safe_load(content)
	assert isinstance(doc, dict), "jtbd-lint.yml must parse as a YAML mapping"


def test_jtbd_lint_workflow_has_required_keys() -> None:
	"""jtbd-lint.yml must have 'on', 'jobs' keys and reference the quality/compliance steps."""
	content = _JTBD_LINT_WORKFLOW.read_text(encoding="utf-8")
	doc = yaml.safe_load(content)
	assert "on" in doc or True in doc, "workflow must have 'on' trigger"
	assert "jobs" in doc
	# Verify v0.4.0 E2 steps are present (quality-score and compliance-lint).
	workflow_text = content
	assert "quality-score" in workflow_text, "jtbd-lint.yml must include quality-score step"
	assert "compliance-lint" in workflow_text, "jtbd-lint.yml must include compliance-lint step"


# ---------------------------------------------------------------------------
# ai-draft fails closed without ANTHROPIC_API_KEY
# ---------------------------------------------------------------------------


def test_ai_draft_fails_closed_without_api_key() -> None:
	"""ai-draft must exit 1 when ANTHROPIC_API_KEY is absent from environment."""
	env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
	result = _run_cli("jtbd", "ai-draft", "A customer files a new insurance claim", env=env)
	assert result.returncode == 1, (
		f"ai-draft should exit 1 without ANTHROPIC_API_KEY, got {result.returncode}\n"
		f"stdout: {result.stdout}\nstderr: {result.stderr}"
	)
	# Must emit a helpful error message, not a traceback.
	combined = result.stdout + result.stderr
	assert "ANTHROPIC_API_KEY" in combined, (
		f"Error message should mention ANTHROPIC_API_KEY. Got:\n{combined}"
	)
