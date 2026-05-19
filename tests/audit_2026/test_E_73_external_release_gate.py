"""Ratchets for fail-closed external release qualification targets."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
	return (ROOT / path).read_text(encoding="utf-8")


def test_audit_workflow_yaml_files_parse() -> None:
	for path in sorted((ROOT / ".github" / "workflows").glob("audit-2026*.yml")):
		parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
		assert isinstance(parsed, dict), f"{path} did not parse to a workflow mapping"


def test_external_release_gate_forbids_local_skip_escapes() -> None:
	makefile = _read("Makefile")

	assert ".PHONY: audit-2026-release-external" in makefile
	assert ".PHONY: audit-2026-release-external-preflight" in makefile
	assert "VISREG_ALLOW_SKIP=1 is forbidden for release qualification" in makefile
	assert "BROWSER_E2E_ALLOW_SKIP=1 is forbidden for release qualification" in makefile
	assert "$(MAKE) audit-2026-release-external-preflight" in makefile
	assert "$(MAKE) audit-2026-visual-regression-dom" in makefile
	assert "$(MAKE) audit-2026-browser-e2e" in makefile
	assert "$(MAKE) audit-2026-ums-parity" in makefile
	assert "FLOWFORGE_REQUIRE_UMS_PARITY" in makefile
	assert "skipping downstream UMS parity" in makefile
	assert "$(MAKE) audit-2026-live-postgres" in makefile


def test_external_release_gate_is_wired_as_manual_release_workflow() -> None:
	workflow = _read(".github/workflows/audit-2026-release-external.yml")

	assert "workflow_dispatch:" in workflow
	assert "pull_request:" not in workflow
	assert "Optional downstream UMS parity is release-" in workflow
	assert "not a package dependency" in workflow
	assert "permissions:" in workflow
	assert "contents: read" in workflow
	assert "backend_repository:" in workflow
	assert "used only when run_ums_parity is true" in workflow
	assert 'default: "nyimbi/ums"' in workflow
	assert "backend_ref:" in workflow
	assert "run_ums_parity:" in workflow
	assert 'default: false' in workflow
	assert "Detect UMS backend checkout token" in workflow
	assert "if: ${{ inputs.run_ums_parity }}" in workflow
	assert "BACKEND_REPOSITORY: ${{ inputs.backend_repository }}" in workflow
	assert "UMS_BACKEND_TOKEN: ${{ secrets.UMS_BACKEND_TOKEN }}" in workflow
	assert "nyimbi/ums is private from GitHub Actions without UMS_BACKEND_TOKEN" in workflow
	assert "attempting public UMS backend checkout without a token" in workflow
	assert "Checkout UMS backend with token" in workflow
	assert "Checkout UMS backend without token" in workflow
	assert (
		"inputs.run_ums_parity && steps.ums-backend-token.outputs.has_token == 'true'"
		in workflow
	)
	assert (
		"inputs.run_ums_parity && steps.ums-backend-token.outputs.has_token == 'false'"
		in workflow
	)
	assert "repository: ${{ inputs.backend_repository }}" in workflow
	assert "ref: ${{ inputs.backend_ref }}" in workflow
	assert workflow.count("persist-credentials: false") >= 3
	assert "token: ${{ secrets.UMS_BACKEND_TOKEN }}" in workflow
	assert "postgres:16" in workflow
	assert "pnpm exec playwright install --with-deps chromium" in workflow
	assert "uv sync --all-packages --all-extras" in workflow
	assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in workflow
	assert "CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}" in workflow
	assert "BACKEND_ROOT: ${{ github.workspace }}/backend" in workflow
	assert "FLOWFORGE_REQUIRE_UMS_PARITY:" in workflow
	assert "FLOWFORGE_TEST_PG_URL:" in workflow
	assert "make audit-2026-release-external" in workflow
	assert "actions/upload-artifact@v4" in workflow
	assert "audit-2026-release-external-evidence" in workflow
	assert "examples/**/screenshots/**/*.dom.html" in workflow
	assert "examples/insurance_claim/jtbd-bundle.json.overrides.json" in workflow
	assert "tests/visual_regression/playwright-report/**" in workflow
	assert "tests/visual_regression/test-results/**" in workflow
	assert "VISREG_ALLOW_SKIP" not in workflow
	assert "BROWSER_E2E_ALLOW_SKIP" not in workflow


def test_dom_baseline_generation_workflow_uploads_reviewable_artifact() -> None:
	workflow = _read(".github/workflows/audit-2026-dom-baselines.yml")

	assert "pull_request:" in workflow
	assert "workflow_dispatch:" in workflow
	assert "DOM_BASELINE_CADENCE:" in workflow
	assert "github.event_name == 'workflow_dispatch' && inputs.cadence || 'smoke'" in workflow
	assert "type: choice" in workflow
	assert "smoke" in workflow
	assert "full" in workflow
	assert "pnpm exec playwright install --with-deps chromium" in workflow
	assert "UPDATE_BASELINES: \"1\"" in workflow
	assert "bash scripts/visual_regression/run_dom_snapshots.sh" in workflow
	assert "actions/upload-artifact@v4" in workflow
	assert "audit-2026-dom-baseline-candidates" in workflow
	assert "examples/**/screenshots/**/*.dom.html" in workflow
	assert "VISREG_ALLOW_SKIP" not in workflow


def test_flowforge_gate_pins_check_all_parallelism() -> None:
	workflow = _read(".github/workflows/flowforge-gate.yml")

	assert "bash scripts/check_all.sh" in workflow
	assert 'FLOWFORGE_CHECK_JOBS: "4"' in workflow
	assert "VISREG_ALLOW_SKIP" not in workflow


def test_ci_workflows_pin_pnpm_11_for_allow_builds() -> None:
	"""pnpm 11 is required for allowBuilds and must run on Node 22+."""

	for path in [
		".github/workflows/audit-2026.yml",
		".github/workflows/audit-2026-dom-baselines.yml",
		".github/workflows/audit-2026-release-external.yml",
		".github/workflows/flowforge-gate.yml",
	]:
		workflow = _read(path)
		assert "pnpm/action-setup@v4" in workflow
		assert 'version: "11.1.3"' in workflow
		assert "actions/setup-node@v4" in workflow
		assert 'node-version: "22"' in workflow


def test_ci_uv_cache_uses_tracked_dependency_files() -> None:
	"""uv.lock is intentionally ignored, so CI must not require it for setup-uv caching."""

	for path in [
		".github/workflows/audit-2026.yml",
		".github/workflows/audit-2026-polish-copy-sidecar.yml",
		".github/workflows/audit-2026-release-external.yml",
		".github/workflows/flowforge-gate.yml",
		".github/workflows/jtbd-lint.yml",
	]:
		workflow = _read(path)
		assert "uv.lock" not in workflow
		assert "pyproject.toml" in workflow


def test_jtbd_lint_workflow_uses_repo_relative_bundle_paths() -> None:
	workflow = _read(".github/workflows/jtbd-lint.yml")

	assert 'uv run flowforge jtbd lint --bundle "$bundle"' in workflow
	assert '--bundle "../$bundle"' not in workflow
	assert 'lint_flags="--warn-only"' in workflow
	assert 'lint_flags="--strict"' in workflow


def test_external_release_preflight_reports_all_hard_prerequisites() -> None:
	script = _read("scripts/audit_2026/check_external_release_preflight.py")
	sidecar = _read("scripts/audit_2026/check_polish_copy_sidecar.py")

	assert "VISREG_ALLOW_SKIP" in script
	assert "BROWSER_E2E_ALLOW_SKIP" in script
	assert "DOM baselines are not checked in" in script
	assert "check_sidecar()" in script
	assert "uv run flowforge polish-copy" in sidecar
	assert "--require-llm --commit" in sidecar
	assert "flowforge-cli[llm]" in sidecar
	assert "FLOWFORGE_POLISH_PROVIDER=claude-cli" in sidecar
	assert "BACKEND_ROOT not found" in script
	assert "FLOWFORGE_REQUIRE_UMS_PARITY" in script
	assert "unset FLOWFORGE_REQUIRE_UMS_PARITY" in script
	assert "FLOWFORGE_TEST_PG_URL" in script
	assert "browser execution is verified by make audit-2026-release-external" in script


def test_external_release_evidence_template_tracks_required_proofs() -> None:
	template = _read("docs/audit-2026/external-release-evidence-template.md")
	runbook = _read("docs/audit-2026/external-release-runbook.md")

	assert "external-release-evidence-template.md" in runbook
	assert "gh workflow run audit-2026-release-external.yml" in runbook
	assert "uv sync --all-packages --all-extras" in runbook
	assert 'uv run python -c "import anthropic"' in runbook
	assert "--require-llm" in runbook
	assert "`polish-copy`" in runbook
	assert "intentionally degrades to a no-op" in runbook
	assert "preflight does not prove browser execution" in runbook
	for required in [
		"Flowforge commit",
		"DOM baseline commit",
		"`VISREG_ALLOW_SKIP` unset",
		"`BROWSER_E2E_ALLOW_SKIP` unset",
		'uv run python -c "import anthropic"',
		"Preflight caveat acknowledged",
		"uv run flowforge polish-copy --require-llm --commit",
		"Workflow run URL",
		"Artifact URL",
		"Browser full-stack Playwright",
		"Real-key polish-copy sidecar gate",
		"UMS workflow-def parity",
		"Live Postgres tenant/ordinal index plan",
	]:
		assert required in template


def test_ums_parity_has_fail_closed_release_target() -> None:
	makefile = _read("Makefile")
	check_all = _read("scripts/check_all.sh")

	assert ".PHONY: audit-2026-ums-parity" in makefile
	assert "BACKEND_ROOT not found" in makefile
	assert "tests/test_workflow_def_parity.py -v --tb=short" in makefile
	assert "audit-2026: \\" in makefile
	assert "audit-2026-ums-parity \\" in makefile
	assert "bash scripts/check_all.sh" in check_all
	assert "path to flowforge repo root" in check_all
	assert "SKIP UMS parity: BACKEND_ROOT not found" in check_all
	assert "audit-2026-ums-parity: BACKEND_ROOT not found" not in check_all
	assert "framework/scripts/check_all.sh" not in check_all
	run_integration = _read("scripts/run_integration.sh")
	assert "bash scripts/run_integration.sh" in run_integration
	assert "path to flowforge repo root" in run_integration
	assert "framework/scripts/run_integration.sh" not in run_integration
