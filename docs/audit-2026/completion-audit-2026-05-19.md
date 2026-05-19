# Audit 2026 completion audit - 2026-05-19

Objective under audit:

Fully resolve `docs/audit-2026/critical-system-gap-audit-2026-05-18.md` and
prove the system is exhaustively tested and correct enough for critical-system
use across host platforms.

Verdict:

Not complete. Local, UMS, live-Postgres, DOM, and browser full-stack evidence
is now strong, including browser-capable GitHub Actions runs. The remaining
blocker is the reviewed real-key copy-polish sidecar, followed by the final
manual external-release bundle run with retained evidence.

## Prompt-to-artifact checklist

| Requirement | Evidence | Status |
|---|---|---|
| Read and understand `HANDOVER.md` | `HANDOVER.md` follow-up list mapped into the audit report and runbook | Done |
| Produce a comprehensive capability/gap audit | `docs/audit-2026/critical-system-gap-audit-2026-05-18.md` covers release-blocking correctness gaps, security/auth issues, durable runtime behavior, workflow gates, UI/UX gaps, package/release posture, and remaining external blockers; this completion audit maps those findings to evidence | Done, with unresolved external blockers |
| Fix/document `scripts/check_all.sh` standalone UMS behavior | `scripts/check_all.sh` skips UMS parity with a reason in standalone checkout; `make audit-2026-ums-parity` fails closed when `BACKEND_ROOT` is missing | Done |
| Verify UMS parity against real backend | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend make audit-2026-ums-parity` -> `156 passed` | Done |
| Add visual-regression dev-server harness | `scripts/visual_regression/run_dom_snapshots.sh` starts `tests/visual_regression/harness/` when `VISREG_DEV_SERVER_URL` is unset | Done |
| Make visual DOM gate fail closed | `bash scripts/visual_regression/run_dom_snapshots.sh smoke` fails when DOM baselines are missing unless `VISREG_ALLOW_SKIP=1` is explicitly set | Done |
| Generate and commit DOM baselines | 21 reviewed smoke `.dom.html` baselines are committed under `examples/insurance_claim/screenshots/**`; `flowforge gate (U24)` run `26077822235` passed with DOM snapshots enabled, and `Audit 2026 DOM baseline generation` run `26077822248` passed in GitHub Actions with Playwright Chromium | Done |
| Run browser full-stack e2e | `.github/workflows/audit-2026-browser-e2e.yml` now runs `make audit-2026-browser-e2e` with Playwright Chromium; GitHub run `26077822269` passed. Local `make audit-2026-browser-e2e` still reaches the generated backend/frontend harness and then fails only because this macOS sandbox blocks Chromium launch with `MachPortRendezvousServer ... Permission denied` | Done in browser-capable CI |
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
| Summarize external release blockers | `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend FLOWFORGE_TEST_PG_URL=postgresql:///flowforge_release_codex_20260519_0506 uv run python scripts/audit_2026/check_external_release_preflight.py` fails closed with only the missing real-key sidecar. The preflight success path says browser execution is verified by `make audit-2026-release-external`, so preflight alone is not treated as release qualification. | Done |
| Retain external release evidence | `docs/audit-2026/external-release-evidence-template.md` captures release candidate, DOM baseline, skip-flag absence, preflight caveat acknowledgement, `anthropic` import check, `uv run flowforge polish-copy --require-llm --commit` review, sidecar review, workflow run, artifact URL, UMS parity, browser e2e, and live Postgres evidence fields; `.github/workflows/audit-2026-release-external.yml` uploads an `audit-2026-release-external-evidence` artifact with DOM baselines, Playwright reports/results, sidecar, and evidence docs when present | Done |
| Verify outbox worker PostgreSQL path | Live Postgres test exposed and then verified PostgreSQL `$N` marker fix in `flowforge_outbox_pg.worker` | Done |
| Keep JS workspace private/source-first decision explicit | `js/README.md` and audit report state no JS package is npm-publishable in this release | Done |
| Remove JS test/toolchain warning noise | JS setup deletes Node's localStorage getter in node tests; stale package-level `.npmrc` removed; `pnpm --dir js test` passed cleanly | Done |
| Run external release bundle | Requires committed DOM baselines, browser e2e, reviewed real-key polish-copy sidecar, UMS parity, and live Postgres evidence; CI is wired and all prerequisite lanes except the real-key sidecar have current evidence. The bundle remains fail-closed until the sidecar is committed and the release workflow is run. | Blocked |

## Remaining blockers

1. `uv run flowforge polish-copy --bundle examples/insurance_claim/jtbd-bundle.json --require-llm --commit`
   must run with a real Anthropic/Claude key, then the sidecar must be reviewed
   and committed if accepted.
2. `make audit-2026-release-external` / `.github/workflows/audit-2026-release-external.yml`
   must run after the sidecar is committed so the retained release artifact ties
   together DOM, browser e2e, sidecar, UMS parity, and live Postgres evidence.

The exact external execution sequence is documented in
`docs/audit-2026/external-release-runbook.md`.

Latest direct blocker verification:

- `flowforge gate (U24)` run `26077822235` passed with committed DOM baselines,
  and `Audit 2026 DOM baseline generation` run `26077822248` passed in
  Playwright-capable GitHub Actions.
- `Audit 2026 browser full-stack e2e` run `26077822269` passed in GitHub
  Actions. A prior run `26077681556` exposed a strict locator ambiguity around
  PII reveal controls; commit `aacdc6f` scopes the browser e2e fields to the
  generated form and exact labels.
- Local `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-browser-e2e`
  starts the generated backend bridge and frontend harness, then fails when
  Chromium launch hits `MachPortRendezvousServer ... Permission denied`; the
  local failure is now an environment limitation, not the release proof source.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-polish-copy-sidecar`
  fails closed because `examples/insurance_claim/jtbd-bundle.json.overrides.json`
  is absent.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend FLOWFORGE_TEST_PG_URL=postgresql:///flowforge_release_codex_20260519_0506 uv run python scripts/audit_2026/check_external_release_preflight.py`
  fails during external preflight, reporting only the missing real-key sidecar.
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
- `gh workflow run .github/workflows/audit-2026-polish-copy-sidecar.yml --repo nyimbi/flowforge --ref audit-2026-critical-readiness -f tone=formal-professional`
  returns `HTTP 404: workflow ... not found on the default branch`, confirming
  GitHub cannot manually dispatch the sidecar helper until that workflow file is
  on the remote default branch.
- `GOPATH=/private/tmp/flowforge-go GOMODCACHE=/private/tmp/flowforge-go/pkg/mod GOCACHE=/private/tmp/flowforge-go/build-cache go run github.com/rhysd/actionlint/cmd/actionlint@latest .github/workflows/audit-2026.yml .github/workflows/audit-2026-dom-baselines.yml .github/workflows/audit-2026-polish-copy-sidecar.yml .github/workflows/audit-2026-release-external.yml .github/workflows/flowforge-gate.yml .github/workflows/jtbd-lint.yml`
  passed, so the PR/default helper and release workflow YAML is validated by
  both `actionlint` and the audit ratchets that inspect required workflow
  structure, trigger, artifact, Node/pnpm, cache, secret, and skip-flag wiring.
