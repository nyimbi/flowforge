# Audit 2026 external release runbook

This runbook covers the release evidence that cannot be completed by the
standalone local gate. Run it in an environment where Chromium can launch and
where the required external credentials are intentionally available.

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
- `BACKEND_ROOT` points at the UMS backend checkout, for example
  `/Users/nyimbiodero/src/pjs/ums/backend`.
- `FLOWFORGE_TEST_PG_URL` points at an isolated disposable Postgres database.
- A valid funded `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY` is set for the real
  `polish-copy` authoring pass.
- The optional Anthropic client is installed for the authoring shell. Use
  `uv sync --all-packages --all-extras` or another environment where
  `uv run python -c "import anthropic"` succeeds; otherwise `polish-copy`
  intentionally degrades to a no-op and will not write a sidecar.
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

## 3. Run real-key polish-copy

Preferred CI-assisted path:

```bash
gh workflow run audit-2026-polish-copy-sidecar.yml -f tone=formal-professional
```

Download and review the `audit-2026-polish-copy-sidecar-candidate` artifact.
Commit `examples/insurance_claim/jtbd-bundle.json.overrides.json` only after
the reviewed copy is acceptable.

Local shell path:

Use the canonical insurance-claim bundle for the first authoring pass:

```bash
uv run python -c "import anthropic"
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

The manual CI path is `.github/workflows/audit-2026-release-external.yml`.
Launch it with:

- `backend_repository`: the UMS backend repository in `owner/repo` form.
- `backend_ref`: the UMS backend git ref to qualify against.
- Repository secrets: valid funded `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`; use
  `UMS_BACKEND_TOKEN` if the backend repository is private and `GITHUB_TOKEN`
  cannot read it.

CLI equivalent:

```bash
gh workflow run audit-2026-release-external.yml \
  -f backend_repository=<owner>/<ums-backend-repo> \
  -f backend_ref=<release-candidate-ref>
```

For a local release rehearsal, run:

```bash
UV_CACHE_DIR=/private/tmp/flowforge-uv-cache \
BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend \
FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres \
make audit-2026-release-external-preflight

UV_CACHE_DIR=/private/tmp/flowforge-uv-cache \
BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend \
FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres \
make audit-2026-release-external
```

Use a CI-specific `FLOWFORGE_TEST_PG_URL` for release CI; the localhost URL
above is only an example for this workstation.

Acceptance criteria:

- `audit-2026-visual-regression-dom` passes with committed baselines.
- `audit-2026-browser-e2e` passes in Chromium.
- `audit-2026-polish-copy-sidecar` passes with a reviewed real-key sidecar.
- `audit-2026-ums-parity` passes against the configured UMS backend.
- `audit-2026-live-postgres` passes against the configured disposable
  Postgres database.
- The workflow uploads the `audit-2026-release-external-evidence` artifact with
  DOM baselines, Playwright reports/results when present, the reviewed sidecar,
  and the evidence/runbook documents.
