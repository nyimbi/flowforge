# Audit 2026 external release runbook

This runbook covers the release evidence that cannot be completed by the
standalone local gate. Run it in an environment where Chromium can launch and
where any required external credentials are intentionally available.

Do not set `VISREG_ALLOW_SKIP=1` or `BROWSER_E2E_ALLOW_SKIP=1` for any command
in this runbook.

`make audit-2026-release-external-preflight` is only a persistent-prerequisite
check; preflight does not prove browser execution. `make
audit-2026-release-external` or `make audit-2026-browser-e2e` must provide that
evidence.

Record the completed evidence in
`docs/audit-2026/external-release-evidence-template.md` or in an equivalent
release approval record.

## Prerequisites

- Chromium-capable shell session, not a sandbox that blocks Playwright process
  launch.
- `BACKEND_ROOT` points at the UMS backend checkout only when
  `FLOWFORGE_REQUIRE_UMS_PARITY=1`, for example
  `/Users/nyimbiodero/src/pjs/ums/backend`.
- `FLOWFORGE_TEST_PG_URL` points at an isolated disposable Postgres database.
- A real LLM authoring path is available for the `polish-copy` pass: either a
  valid funded `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` plus the optional
  Anthropic client, or `FLOWFORGE_POLISH_PROVIDER=claude-cli` with a configured
  Claude CLI.
- For the Anthropic SDK path, use `uv sync --all-packages --all-extras` or
  another environment where `uv run python -c "import anthropic"` succeeds;
  otherwise `polish-copy` intentionally degrades to a no-op and will not write a
  sidecar.
- `UV_CACHE_DIR` points at a writable cache path when the default user cache is
  not writable.

## 1. Generate and commit DOM baselines

Preferred CI-assisted path:

On pull requests, `.github/workflows/audit-2026-dom-baselines.yml` generates a
smoke-cadence `audit-2026-dom-baseline-candidates` artifact automatically when
visual-regression inputs change. Use that artifact for early browser evidence
before the helper is available on the default branch.

```bash
gh workflow run audit-2026-dom-baselines.yml -f cadence=full
```

Download and review the `audit-2026-dom-baseline-candidates` artifact, then
apply and commit the reviewed `.dom.html` files under `examples/*/screenshots/`.

Local/browser-capable shell path:

Run the smoke baseline first:

```bash
UPDATE_BASELINES=1 bash scripts/visual_regression/run_dom_snapshots.sh smoke
bash scripts/visual_regression/run_dom_snapshots.sh smoke
```

Then run the full baseline set:

```bash
UPDATE_BASELINES=1 bash scripts/visual_regression/run_dom_snapshots.sh full
bash scripts/visual_regression/run_dom_snapshots.sh full
```

Review and commit the generated files under `examples/*/screenshots/`.

Acceptance criteria:

- The checked-in baseline tree contains real `.dom.html` files, not only
  `.gitkeep` placeholders.
- The wrapper passes without `UPDATE_BASELINES=1`.
- The wrapper passes without `VISREG_ALLOW_SKIP=1`.

## 2. Run browser full-stack e2e

Preferred PR/CI path:

`.github/workflows/audit-2026-browser-e2e.yml` runs the same target in a
Playwright-capable GitHub runner and uploads browser evidence artifacts.

Local/browser-capable shell path:

```bash
make audit-2026-browser-e2e
```

Acceptance criteria:

- Playwright Chromium launches successfully.
- The generated insurance-claim frontend submits `submit` and `approve`
  through the generated FastAPI-router bridge.
- The test verifies `Idempotency-Key`, `X-Tenant-Id`, request bodies, and
  `review -> done` responses.

## 3. Run LLM polish-copy

Preferred CI-assisted path:

```bash
gh workflow run audit-2026-polish-copy-sidecar.yml -f tone=formal-professional
```

Download and review the `audit-2026-polish-copy-sidecar-candidate` artifact.
Commit `examples/insurance_claim/jtbd-bundle.json.overrides.json` only after
the reviewed copy is acceptable.

Local shell path, Anthropic SDK:

Use the canonical insurance-claim bundle for the first authoring pass:

```bash
uv run python -c "import anthropic"
uv run flowforge polish-copy \
  --bundle examples/insurance_claim/jtbd-bundle.json \
  --tone formal-professional \
  --require-llm \
  --commit
```

Local shell path, configured Claude CLI:

```bash
FLOWFORGE_POLISH_PROVIDER=claude-cli \
FLOWFORGE_POLISH_CLAUDE_MODEL=sonnet \
FLOWFORGE_POLISH_CLAUDE_MAX_BUDGET_USD=0.50 \
uv run flowforge polish-copy \
  --bundle examples/insurance_claim/jtbd-bundle.json \
  --tone formal-professional \
  --require-llm \
  --commit
```

Review the resulting sidecar before committing it:

```bash
git diff -- examples/insurance_claim/jtbd-bundle.json.overrides.json
uv run pytest python/flowforge-cli/tests/test_polish_copy.py -q --tb=short
make audit-2026-polish-copy-sidecar
```

Acceptance criteria:

- The sidecar is reviewed by a human before commit.
- The sidecar records `llm_provider`, `llm_model`, and `prompt_sha256`.
- No canonical JTBD bundle bytes change.

## 4. Run external release bundle

The CI path is `.github/workflows/audit-2026-release-external.yml`. It is a
manual, release-only workflow for Flowforge evidence that cannot be proven in a
standalone local gate: browser DOM baselines, browser full-stack e2e, reviewed
sidecar verification, and live Postgres checks. UMS is downstream compatibility
evidence, not a Flowforge package dependency. Run UMS parity only when a
release candidate explicitly needs UMS certification.

For a specific release-candidate backend ref, launch the manual path with:

- `run_ums_parity`: set to `true` only for downstream UMS certification.
- `backend_repository`: the UMS backend repository in `owner/repo` form; used
  only when `run_ums_parity=true`.
- `backend_ref`: the UMS backend git ref to qualify against; used only when
  `run_ums_parity=true`.
- Optional repository secret: `UMS_BACKEND_TOKEN` with read access to the UMS
  backend. This is only needed when the selected backend repository is private.
  `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` are only needed if the release workflow
  is also being used to author a fresh sidecar; once a reviewed sidecar is
  committed, the external release target verifies it without calling an LLM
  provider.

If the selected backend repository is private, use a purpose-specific UMS read
token for `UMS_BACKEND_TOKEN`; do not reuse a broad local `gh auth token`
unless that risk is explicitly accepted. From a shell where the token is already
present in the environment:

```bash
test -n "${FLOWFORGE_UMS_READ_TOKEN:-}"
gh secret set UMS_BACKEND_TOKEN \
  --repo nyimbi/flowforge \
  --body "$FLOWFORGE_UMS_READ_TOKEN"
```

Then launch the manual release workflow:

```bash
gh workflow run audit-2026-release-external.yml \
  -f run_ums_parity=true \
  -f backend_repository=nyimbi/ums \
  -f backend_ref=main
```

For independent Flowforge release qualification, leave `run_ums_parity=false`
or omit it:

```bash
gh workflow run audit-2026-release-external.yml \
  --repo nyimbi/flowforge \
  --ref audit-2026-critical-readiness
```

If a private-backend manual release run failed because the secret was missing or
could not read the selected repository, rerun only the failed jobs after the
secret is configured:

```bash
gh run rerun <failed-run-id> --repo nyimbi/flowforge --failed
```

For a local release rehearsal, run:

```bash
UV_CACHE_DIR=/private/tmp/flowforge-uv-cache \
FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres \
make audit-2026-release-external-preflight

UV_CACHE_DIR=/private/tmp/flowforge-uv-cache \
FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres \
make audit-2026-release-external
```

Use a CI-specific `FLOWFORGE_TEST_PG_URL` for release CI; the localhost URL
above is only an example for this workstation.

To include downstream UMS parity in the same local run, add:

```bash
FLOWFORGE_REQUIRE_UMS_PARITY=1 \
BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend
```

Acceptance criteria:

- `audit-2026-visual-regression-dom` passes with committed baselines.
- `audit-2026-browser-e2e` passes in Chromium.
- `audit-2026-polish-copy-sidecar` passes with a reviewed LLM-generated
  sidecar.
- If `run_ums_parity=true` or `FLOWFORGE_REQUIRE_UMS_PARITY=1`,
  `audit-2026-ums-parity` passes against the configured UMS backend.
- `audit-2026-live-postgres` passes against the configured disposable
  Postgres database.
- The workflow uploads the `audit-2026-release-external-evidence` artifact with
  uploadable PyPI `dist/*` artifacts, the PyPI artifact checksum manifest, DOM
  baselines, Playwright reports/results when present, the reviewed sidecar, and
  the evidence/runbook documents.
