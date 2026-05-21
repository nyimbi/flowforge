"""Ratchets for the browser-backed full-stack Playwright lane."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
	return (ROOT / path).read_text(encoding="utf-8")


def test_browser_full_stack_gate_is_wired_to_makefile_and_runner() -> None:
	makefile = _read("Makefile")
	run_integration = _read("scripts/run_integration.sh")
	wrapper = _read("scripts/run_browser_full_stack.sh")

	assert ".PHONY: audit-2026-browser-e2e" in makefile
	assert "bash scripts/run_browser_full_stack.sh" in makefile
	assert "RUN_BROWSER_E2E" in run_integration
	assert "scripts/run_browser_full_stack.sh" in run_integration
	assert "FLOWFORGE_BROWSER_E2E_REQUIRE=1" in wrapper
	assert "--project=browser-full-stack" in wrapper
	assert "NEXT_PUBLIC_FLOWFORGE_API_BASE_URL" in wrapper


def test_browser_gate_wrappers_explain_local_chromium_failures() -> None:
	wrapper = _read("scripts/run_browser_full_stack.sh")
	dom_wrapper = _read("scripts/visual_regression/run_dom_snapshots.sh")

	for script in (wrapper, dom_wrapper):
		assert "PLAYWRIGHT_LOG" in script
		assert "Executable doesn't exist" in script
		assert "Looks like Playwright was just installed" in script
		assert "npx playwright install" in script
		assert "pnpm exec playwright install chromium" in script
		assert "MachPortRendezvousServer.*Permission denied" in script
		assert "browser-capable CI runner" in script


def test_browser_full_stack_playwright_project_targets_generated_flow() -> None:
	config = _read("tests/visual_regression/playwright.config.ts")
	spec = _read("tests/visual_regression/tests/e2e_full_stack.spec.ts")
	vite = _read("tests/visual_regression/harness/vite.config.ts")

	assert 'name: "browser-full-stack"' in config
	assert "e2e_full_stack\\.spec\\.ts" in config
	assert "harnessUrl(" in spec
	assert '"insurance_claim"' in spec
	assert '"claim-intake"' in spec
	assert "page.route(" not in spec
	assert "Idempotency-Key" not in spec
	assert 'headers["idempotency-key"]' in spec
	assert 'headers["x-tenant-id"]' in spec
	assert 'state: "review"' in spec
	assert 'state: "done"' in spec
	assert "process.env.NEXT_PUBLIC_FLOWFORGE_API_BASE_URL" in vite


def test_generated_backend_bridge_uses_real_fastapi_router_not_js_mock() -> None:
	bridge = _read("tests/integration/browser/generated_backend_server.py")

	assert "ThreadingHTTPServer" in bridge
	assert "TestClient(_build_app())" in bridge
	assert "app.include_router(claim_intake_router.router)" in bridge
	assert "dependency_overrides[claim_intake_router.require_principal]" in bridge
	assert "reset_runtime_state()" in bridge
	assert "reset_idempotency_store()" in bridge
	assert "CLIENT.post(" in bridge
