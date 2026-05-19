# Audit 2026 completion audit - 2026-05-19

Objective under audit:

Fully resolve `docs/audit-2026/critical-system-gap-audit-2026-05-18.md` and
prove the system is exhaustively tested and correct enough for critical-system
use across host platforms.

Verdict:

Not complete. Local, UMS, live-Postgres, DOM, browser full-stack, and reviewed
copy-polish sidecar evidence is now strong, including browser-capable GitHub
Actions runs for the browser lanes. The remaining blocker is the final
external-release bundle run with retained evidence in an environment where
Chromium can launch and where the selected UMS backend checkout is accessible
(public repository checkout, or `UMS_BACKEND_TOKEN` for a private backend).

## Prompt-to-artifact checklist

| Requirement | Evidence | Status |
|---|---|---|
| Read and understand `HANDOVER.md` | `HANDOVER.md` follow-up list mapped into the audit report and runbook | Done |
| Produce a comprehensive capability/gap audit | `docs/audit-2026/critical-system-gap-audit-2026-05-18.md` covers release-blocking correctness gaps, security/auth issues, durable runtime behavior, workflow gates, UI/UX gaps, package/release posture, and remaining external blockers; this completion audit maps those findings to evidence | Done, with unresolved external blockers |
| Fix/document `scripts/check_all.sh` standalone UMS behavior | `scripts/check_all.sh` skips UMS parity with a reason in standalone checkout; `make audit-2026-ums-parity` fails closed when `BACKEND_ROOT` is missing | Done |
| Verify UMS parity against real backend | Fresh clone `git clone https://github.com/nyimbi/ums /private/tmp/flowforge-ums-release-backend`; `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend make audit-2026-ums-parity` -> `134 passed` | Done |
| Add visual-regression dev-server harness | `scripts/visual_regression/run_dom_snapshots.sh` starts `tests/visual_regression/harness/` when `VISREG_DEV_SERVER_URL` is unset | Done |
| Make visual DOM gate fail closed | `bash scripts/visual_regression/run_dom_snapshots.sh smoke` fails when DOM baselines are missing unless `VISREG_ALLOW_SKIP=1` is explicitly set | Done |
| Generate and commit DOM baselines | 21 reviewed smoke `.dom.html` baselines are committed under `examples/insurance_claim/screenshots/**`; PR evidence includes `flowforge end-to-end gate` run `26095391068` and `Audit 2026 DOM baseline generation` run `26095391144` passing in GitHub Actions with Playwright Chromium | Done |
| Run browser full-stack e2e | `.github/workflows/audit-2026-browser-e2e.yml` now runs `make audit-2026-browser-e2e` with Playwright Chromium; PR evidence includes GitHub run `26095391083` passing. Local `make audit-2026-browser-e2e` still reaches the generated backend/frontend harness and then fails only because this macOS sandbox blocks Chromium launch with `MachPortRendezvousServer ... Permission denied` | Done in browser-capable CI |
| Fill fr-CA translations | `uv run python scripts/i18n/check_coverage.py` via release-local -> `0 error(s), 0 warning(s)` | Done |
| Run first real `polish-copy` sidecar | `FLOWFORGE_POLISH_PROVIDER=claude-cli FLOWFORGE_POLISH_CLAUDE_MODEL=sonnet FLOWFORGE_POLISH_CLAUDE_MAX_BUDGET_USD=0.50 UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge polish-copy --bundle examples/insurance_claim/jtbd-bundle.json --tone formal-professional --require-llm --commit` ran through the configured Claude CLI and wrote `examples/insurance_claim/jtbd-bundle.json.overrides.json` with `llm_provider=claude-cli`, `llm_model=sonnet`, and `prompt_sha256=e4656e96c6234648ab64fe11fd00cb2c45d1b29f83f43d3e90ef63c04b48b09a`; `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-polish-copy-sidecar` passed | Done |
| Verify optional LLM extra is installable | `uv sync --all-packages --all-extras` installed `anthropic==0.100.0`; `uv run python -c "import anthropic; print('anthropic import ok')"` passed | Done |
| Preserve `polish-copy` audit metadata and fail-closed authoring semantics | `uv run pytest python/flowforge-cli/tests/test_polish_copy.py -q --tb=short` -> `32 passed`, covering metadata stamping, provider-format failure, invalid provider/auth failure without traceback, Claude CLI success/failure handling, no-op `--require-llm` failure, and preservation of existing reviewed sidecars; focused sidecar/audit suite `python/flowforge-cli/tests/test_polish_copy.py tests/audit_2026/test_E_75_polish_copy_release_gate.py tests/v0_3_0/test_polish_copy_committed_overrides.py` -> `46 passed`; full CLI package suite -> `603 passed, 1 skipped` | Done |
| Add W4b generator property coverage | `uv run pytest tests/audit_2026/test_property_coverage_gate.py` via release-local -> passed; W4b `i18n` and `operator_manual` included | Done |
| Run local full gate | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache VISREG_ALLOW_SKIP=1 bash scripts/check_all.sh` -> `U24 gate PASSED`, 46 Python packages, 7 JS packages, 2,668 counted tests/assertions, elapsed 115s on the latest rerun | Done with documented local visual skip |
| Run fail-closed local release gate | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-local` -> fail-closed local release gate passed; covered ratchets, 11 conformance tests, 195 audit tests, Python+JS cross-runtime parity, edge cases, PromQL lint, W4b property coverage, i18n coverage, and signoff mapping, while still printing browser DOM, browser e2e, reviewed sidecar, UMS parity, and live Postgres as external release checks | Done |
| Run audit ratchets | `uv run pytest tests/audit_2026 -q --tb=short` -> `200 passed`, including the new workflow helper ratchets and YAML parse coverage | Done |
| Verify PR check state after workflow token change | `gh pr checks 1 --repo nyimbi/flowforge --watch` on commit `4ed3639` returned all PR checks passing: JTBD lint, security ratchets, signoff, audit-2026 unit/conformance/property/e2e/edge/cross-runtime, browser full-stack, flowforge end-to-end gate, and DOM baseline generation. Nightly SLA stress is intentionally skipped on pull requests. | Done |
| Run live Postgres release checks | `FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres make audit-2026-live-postgres` -> `4 passed`, including stale snapshot rejection, SKIP LOCKED outbox drain, interleaved-tenant audit verification, and tenant/ordinal index-plan coverage | Done |
| Wire external release CI | `.github/workflows/audit-2026-release-external.yml` provides a manual, release-only workflow with caller-supplied UMS checkout input, optional UMS checkout token for private backends, Postgres service, flowforge all-extras sync, Playwright Chromium install, LLM secret wiring, and `make audit-2026-release-external`; `tests/audit_2026/test_E_73_external_release_gate.py` ratchets that it is not a pull-request dependency | Done |
| Keep GitHub CI runnable from a source checkout | Workflow setup now uses tracked `pyproject.toml` cache dependency inputs instead of ignored `uv.lock`, pnpm 11 jobs run on Node 22, pyright is installed through `uv run --with pyright`, and JTBD lint passes repo-relative bundle paths to the CLI in advisory mode unless `JTBD_LINT_STRICT=true`; the external-release ratchet covers these requirements | Done |
| Reject release skip escape hatches | `VISREG_ALLOW_SKIP=1 make audit-2026-release-external` exits nonzero with `VISREG_ALLOW_SKIP=1 is forbidden for release qualification`; `BROWSER_E2E_ALLOW_SKIP=1 make audit-2026-release-external` exits nonzero with `BROWSER_E2E_ALLOW_SKIP=1 is forbidden for release qualification` | Done |
| Summarize external release blockers | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend FLOWFORGE_TEST_PG_URL=postgresql:///flowforge_release_codex_20260519_0506 uv run python scripts/audit_2026/check_external_release_preflight.py` passes after the reviewed sidecar is present. The preflight success path says browser execution is verified by `make audit-2026-release-external`, so preflight alone is not treated as release qualification. | Done |
| Retain external release evidence | `docs/audit-2026/external-release-evidence-template.md` captures release candidate, DOM baseline, skip-flag absence, preflight caveat acknowledgement, `anthropic` import check, `uv run flowforge polish-copy --require-llm --commit` review, sidecar review, workflow run, artifact URL, UMS parity, browser e2e, and live Postgres evidence fields; `.github/workflows/audit-2026-release-external.yml` uploads an `audit-2026-release-external-evidence` artifact with DOM baselines, Playwright reports/results, sidecar, and evidence docs when present | Done |
| Verify outbox worker PostgreSQL path | Live Postgres test exposed and then verified PostgreSQL `$N` marker fix in `flowforge_outbox_pg.worker` | Done |
| Keep JS workspace private/source-first decision explicit | `js/README.md` and audit report state no JS package is npm-publishable in this release | Done |
| Remove JS test/toolchain warning noise | JS setup deletes Node's localStorage getter in node tests; stale package-level `.npmrc` removed; `pnpm --dir js test` passed cleanly | Done |
| Run external release bundle | Requires committed DOM baselines, browser e2e, reviewed polish-copy sidecar, UMS parity, and live Postgres evidence. A local run with fresh UMS clone `BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend` and `FLOWFORGE_TEST_PG_URL` supplied reaches `audit-2026-visual-regression-dom`; all 21 browser-backed DOM cases fail at Chromium launch with `MachPortRendezvousServer ... Permission denied`, while 3 non-browser metadata checks pass. Manual GitHub Actions run `26095402727` proved the selected `nyimbi/ums` backend is not readable by Actions without `UMS_BACKEND_TOKEN` (`repository not found`) and failed before the release gate. The workflow is manual/release-only so downstream UMS compatibility does not block ordinary Flowforge pull requests. | Blocked |

## Remaining blockers

1. `make audit-2026-release-external` / `.github/workflows/audit-2026-release-external.yml`
   must run in a browser-capable release environment so the retained release
   artifact ties together DOM, browser e2e, sidecar, UMS parity, and live
   Postgres evidence.
2. If the selected UMS backend repository is private, repository secret
   `UMS_BACKEND_TOKEN` must be configured with read access to that backend.

The exact external execution sequence is documented in
`docs/audit-2026/external-release-runbook.md`.

Direct blocker evidence:

- Recent PR checks on commit `4ed3639` are green: `flowforge end-to-end gate` run
  `26095391068`, `Audit 2026 DOM baseline generation` run `26095391144`, and
  `Audit 2026 browser full-stack e2e` run `26095391083` passed in
  Playwright-capable GitHub Actions.
- Local `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-browser-e2e`
  starts the generated backend bridge and frontend harness, then fails when
  Chromium launch hits `MachPortRendezvousServer ... Permission denied`; the
  local failure is now an environment limitation, not the release proof source.
- `FLOWFORGE_POLISH_PROVIDER=claude-cli FLOWFORGE_POLISH_CLAUDE_MODEL=sonnet FLOWFORGE_POLISH_CLAUDE_MAX_BUDGET_USD=0.50 UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge polish-copy --bundle examples/insurance_claim/jtbd-bundle.json --tone formal-professional --require-llm --commit`
  wrote the reviewed sidecar with Claude CLI metadata.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-polish-copy-sidecar`
  passes with `examples/insurance_claim/jtbd-bundle.json.overrides.json`.
- Fresh UMS clone `/private/tmp/flowforge-ums-release-backend` is at
  `cae102c91eda1553dfc234a87a16cc396cf51ea1` on `main`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend make audit-2026-ums-parity`
  passes with `134 passed`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend FLOWFORGE_TEST_PG_URL=postgresql:///flowforge_release_codex_20260519_0506 uv run python scripts/audit_2026/check_external_release_preflight.py`
  passes; the success message explicitly says browser execution is verified by
  `make audit-2026-release-external`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend FLOWFORGE_TEST_PG_URL=postgresql:///flowforge_release_codex_20260519_0506 make audit-2026-release-external`
  reaches the DOM browser lane; 21 browser-backed DOM checks fail only because
  local Chromium launch is blocked by `MachPortRendezvousServer ... Permission
  denied`, while the 3 metadata checks pass.
- The remediation branch has been pushed as `audit-2026-critical-readiness`.
  Earlier PR execution of `audit-2026-release-external` exposed that
  downstream UMS access made an independent Flowforge pull request look blocked
  on a private backend token. The workflow is now manual/release-only and can
  check out public UMS backends without a token; `UMS_BACKEND_TOKEN` is only
  needed for private backend repositories.
- Manual external release run `26095402727` on `audit-2026-critical-readiness`
  with `backend_repository=nyimbi/ums` and no `UMS_BACKEND_TOKEN` failed during
  checkout with `repository 'https://github.com/nyimbi/ums/' not found`, so the
  selected backend is private from the GitHub Actions runner's perspective.
- `.github/workflows/audit-2026-dom-baselines.yml` now also runs on pull
  requests with smoke cadence, so this branch can produce reviewable DOM
  baseline artifacts before the manual helper is registered on `main`.
- `docker info` reports Docker CLI is installed but cannot connect to the Docker
  daemon. The approval request to launch Docker Desktop was rejected, so the
  local Linux-container fallback for Chromium execution is unavailable in this
  session.
- `gh workflow run .github/workflows/audit-2026-polish-copy-sidecar.yml --repo nyimbi/flowforge --ref audit-2026-critical-readiness -f tone=formal-professional`
  returns `HTTP 404: workflow ... not found on the default branch`, confirming
  GitHub cannot manually dispatch the sidecar helper until that workflow file is
  on the remote default branch.
- `GOPATH=/private/tmp/flowforge-go GOMODCACHE=/private/tmp/flowforge-go/pkg/mod GOCACHE=/private/tmp/flowforge-go/build-cache go run github.com/rhysd/actionlint/cmd/actionlint@latest .github/workflows/audit-2026.yml .github/workflows/audit-2026-dom-baselines.yml .github/workflows/audit-2026-polish-copy-sidecar.yml .github/workflows/audit-2026-release-external.yml .github/workflows/flowforge-gate.yml .github/workflows/jtbd-lint.yml`
  passed, so the PR/default helper and release workflow YAML is validated by
  both `actionlint` and the audit ratchets that inspect required workflow
  structure, trigger, artifact, Node/pnpm, cache, secret, and skip-flag wiring.
