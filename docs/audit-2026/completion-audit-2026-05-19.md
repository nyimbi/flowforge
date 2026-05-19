# Audit 2026 completion audit - 2026-05-19

Objective under audit:

Fully resolve `docs/audit-2026/critical-system-gap-audit-2026-05-18.md` and
prove the system is exhaustively tested and correct enough for critical-system
use across host platforms.

Verdict:

Not complete. Local, UMS, and live-Postgres evidence is strong, but browser
baselines/browser e2e and real-key copy-polish remain unverified in this
sandbox.

## Prompt-to-artifact checklist

| Requirement | Evidence | Status |
|---|---|---|
| Read and understand `HANDOVER.md` | `HANDOVER.md` follow-up list mapped into the audit report and runbook | Done |
| Produce a comprehensive capability/gap audit | `docs/audit-2026/critical-system-gap-audit-2026-05-18.md` covers release-blocking correctness gaps, security/auth issues, durable runtime behavior, workflow gates, UI/UX gaps, package/release posture, and remaining external blockers; this completion audit maps those findings to evidence | Done, with unresolved external blockers |
| Fix/document `scripts/check_all.sh` standalone UMS behavior | `scripts/check_all.sh` skips UMS parity with a reason in standalone checkout; `make audit-2026-ums-parity` fails closed when `BACKEND_ROOT` is missing | Done |
| Verify UMS parity against real backend | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend make audit-2026-ums-parity` -> `156 passed` | Done |
| Add visual-regression dev-server harness | `scripts/visual_regression/run_dom_snapshots.sh` starts `tests/visual_regression/harness/` when `VISREG_DEV_SERVER_URL` is unset | Done |
| Make visual DOM gate fail closed | `bash scripts/visual_regression/run_dom_snapshots.sh smoke` fails when DOM baselines are missing unless `VISREG_ALLOW_SKIP=1` is explicitly set | Done |
| Generate and commit DOM baselines | `UPDATE_BASELINES=1 bash scripts/visual_regression/run_dom_snapshots.sh smoke` starts the local Vite harness at `http://127.0.0.1:5173/` and passes 3 metadata tests, but all 21 browser-backed DOM cases fail when Chromium launch hits `MachPortRendezvousServer ... Permission denied`; `find examples -path '*screenshots*' -name '*.dom.html' -print` returns no files; the unsandboxed baseline-generation rerun request was rejected by the approval layer; `.github/workflows/audit-2026-dom-baselines.yml` now provides a manual Chromium-capable artifact-generation path for reviewed baseline candidates | Blocked |
| Run browser full-stack e2e | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-browser-e2e` starts backend/frontend harnesses but Chromium launch fails with `MachPortRendezvousServer ... Permission denied`; the unsandboxed rerun request was rejected by the approval layer | Blocked |
| Fill fr-CA translations | `uv run python scripts/i18n/check_coverage.py` via release-local -> `0 error(s), 0 warning(s)` | Done |
| Run first real `polish-copy` sidecar | `uv run flowforge polish-copy --bundle examples/insurance_claim/jtbd-bundle.json --tone formal-professional --require-llm --commit` fails closed because no `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY` is set and writes no sidecar; `test -f examples/insurance_claim/jtbd-bundle.json.overrides.json` fails; `make audit-2026-polish-copy-sidecar` now fails closed while the sidecar is absent; `.github/workflows/audit-2026-polish-copy-sidecar.yml` now provides a manual real-key authoring path that uploads a reviewable sidecar candidate | Blocked |
| Verify optional LLM extra is installable | `uv sync --all-packages --all-extras` installed `anthropic==0.100.0`; `uv run python -c "import anthropic; print('anthropic import ok')"` passed | Done |
| Preserve `polish-copy` audit metadata and fail-closed authoring semantics | `uv run pytest python/flowforge-cli/tests/test_polish_copy.py -q --tb=short` -> `29 passed`, covering metadata stamping, provider-format failure, no-op `--require-llm` failure, and preservation of existing reviewed sidecars; `uv run pytest tests/audit_2026/test_E_75_polish_copy_release_gate.py -q --tb=short` -> `7 passed`, covering release-gate metadata validation, bad-metadata rejection, empty-string rejection, and dead-key rejection | Done |
| Add W4b generator property coverage | `uv run pytest tests/audit_2026/test_property_coverage_gate.py` via release-local -> passed; W4b `i18n` and `operator_manual` included | Done |
| Run local full gate | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache VISREG_ALLOW_SKIP=1 bash scripts/check_all.sh` -> `U24 gate PASSED`, 46 Python packages, 7 JS packages, 2,665 counted tests/assertions, elapsed 86s on the latest rerun | Done with documented local visual skip |
| Run fail-closed local release gate | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-local` -> fail-closed local release gate passed; covered ratchets, 11 conformance tests, 195 audit tests, Python+JS cross-runtime parity, edge cases, PromQL lint, W4b property coverage, i18n coverage, and signoff mapping, while still printing browser DOM, browser e2e, real-key sidecar, UMS parity, and live Postgres as external release checks | Done |
| Run audit ratchets | `uv run pytest tests/audit_2026 -q --tb=short` -> `200 passed`, including the new workflow helper ratchets and YAML parse coverage | Done |
| Run live Postgres release checks | `FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres make audit-2026-live-postgres` -> `4 passed`, including stale snapshot rejection, SKIP LOCKED outbox drain, interleaved-tenant audit verification, and tenant/ordinal index-plan coverage | Done |
| Wire external release CI | `.github/workflows/audit-2026-release-external.yml` provides a manual workflow with UMS checkout input, Postgres service, flowforge all-extras sync, Playwright Chromium install, LLM secret wiring, and `make audit-2026-release-external`; `tests/audit_2026/test_E_73_external_release_gate.py` ratchets it | Done |
| Keep GitHub CI runnable from a source checkout | Workflow setup now uses tracked `pyproject.toml` cache dependency inputs instead of ignored `uv.lock`, pnpm 11 jobs run on Node 22, pyright is installed through `uv run --with pyright`, and JTBD lint passes repo-relative bundle paths to the CLI in advisory mode unless `JTBD_LINT_STRICT=true`; the external-release ratchet covers these requirements | Done |
| Reject release skip escape hatches | `VISREG_ALLOW_SKIP=1 make audit-2026-release-external` exits nonzero with `VISREG_ALLOW_SKIP=1 is forbidden for release qualification`; `BROWSER_E2E_ALLOW_SKIP=1 make audit-2026-release-external` exits nonzero with `BROWSER_E2E_ALLOW_SKIP=1 is forbidden for release qualification` | Done |
| Summarize external release blockers | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-external-preflight` fails closed and reports all current persistent prerequisite blockers together; with `BACKEND_ROOT` and `FLOWFORGE_TEST_PG_URL` supplied, the remaining preflight blockers are only missing DOM baselines and a missing real-key sidecar produced by `uv run flowforge polish-copy --require-llm --commit` with a key and `flowforge-cli[llm]` installed. The preflight success path now says browser execution is verified by `make audit-2026-release-external`, so preflight alone is not treated as release qualification. | Done |
| Retain external release evidence | `docs/audit-2026/external-release-evidence-template.md` captures release candidate, DOM baseline, skip-flag absence, preflight caveat acknowledgement, `anthropic` import check, `uv run flowforge polish-copy --require-llm --commit` review, sidecar review, workflow run, artifact URL, UMS parity, browser e2e, and live Postgres evidence fields; `.github/workflows/audit-2026-release-external.yml` uploads an `audit-2026-release-external-evidence` artifact with DOM baselines, Playwright reports/results, sidecar, and evidence docs when present | Done |
| Verify outbox worker PostgreSQL path | Live Postgres test exposed and then verified PostgreSQL `$N` marker fix in `flowforge_outbox_pg.worker` | Done |
| Keep JS workspace private/source-first decision explicit | `js/README.md` and audit report state no JS package is npm-publishable in this release | Done |
| Remove JS test/toolchain warning noise | JS setup deletes Node's localStorage getter in node tests; stale package-level `.npmrc` removed; `pnpm --dir js test` passed cleanly | Done |
| Run external release bundle | Requires committed DOM baselines, browser e2e, reviewed real-key polish-copy sidecar, UMS parity, and live Postgres evidence; CI is wired but still fail-closed until browser and sidecar evidence exists | Blocked |

## Remaining blockers

1. Browser DOM baselines must be generated, reviewed, committed, and verified
   without `VISREG_ALLOW_SKIP=1`.
2. `make audit-2026-browser-e2e` must pass in Chromium without
   `BROWSER_E2E_ALLOW_SKIP=1`.
3. `uv run flowforge polish-copy --bundle examples/insurance_claim/jtbd-bundle.json --require-llm --commit`
   must run with a real Anthropic/Claude key, then the sidecar must be reviewed
   and committed if accepted.

The exact external execution sequence is documented in
`docs/audit-2026/external-release-runbook.md`.

Latest direct blocker verification:

- `bash scripts/visual_regression/run_dom_snapshots.sh smoke` fails closed
  because DOM baselines are not checked in and `VISREG_ALLOW_SKIP=1` is not set.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-browser-e2e`
  starts the generated backend bridge and frontend harness, then fails when
  Chromium launch hits `MachPortRendezvousServer ... Permission denied`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-polish-copy-sidecar`
  fails closed because `examples/insurance_claim/jtbd-bundle.json.overrides.json`
  is absent.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres make audit-2026-release-external`
  fails during external preflight before browser execution, reporting only the
  missing DOM baselines and missing real-key sidecar.
- `uv run flowforge polish-copy --bundle examples/insurance_claim/jtbd-bundle.json --tone formal-professional --require-llm --commit`
  fails closed because no `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY` is exported,
  and writes no sidecar.
- The remediation branch has been pushed as
  `audit-2026-critical-readiness`. `gh workflow list --repo nyimbi/flowforge`
  still shows only the older remote `Audit 2026`, `flowforge gate`, and `JTBD
  lint` workflows because the new manual external release and sidecar-authoring
  workflows are not on the default branch yet.
- `.github/workflows/audit-2026-dom-baselines.yml` now also runs on pull
  requests with smoke cadence, so this branch can produce reviewable DOM
  baseline artifacts before the manual helper is registered on `main`.
- `docker info` reports Docker CLI is installed but cannot connect to the Docker
  daemon. The approval request to launch Docker Desktop was rejected, so the
  local Linux-container fallback for Chromium execution is unavailable in this
  session.
- `gh workflow run audit-2026-dom-baselines.yml --repo nyimbi/flowforge --ref main -f cadence=smoke`
  returns `HTTP 404: workflow audit-2026-dom-baselines.yml not found on the
  default branch`, confirming GitHub cannot manually dispatch the full-cadence
  helper workflow until the workflow file is pushed to the remote default
  branch.
- `gh secret list --repo nyimbi/flowforge` returns no configured repository
  secrets, so the sidecar-authoring and external-release workflows also need
  `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY` to be added before real-key
  `polish-copy` can run in GitHub Actions.
- `GOPATH=/private/tmp/flowforge-go GOMODCACHE=/private/tmp/flowforge-go/pkg/mod GOCACHE=/private/tmp/flowforge-go/build-cache go run github.com/rhysd/actionlint/cmd/actionlint@latest .github/workflows/audit-2026.yml .github/workflows/audit-2026-dom-baselines.yml .github/workflows/audit-2026-polish-copy-sidecar.yml .github/workflows/audit-2026-release-external.yml .github/workflows/flowforge-gate.yml .github/workflows/jtbd-lint.yml`
  passed, so the PR/default helper and release workflow YAML is validated by
  both `actionlint` and the audit ratchets that inspect required workflow
  structure, trigger, artifact, Node/pnpm, cache, secret, and skip-flag wiring.
