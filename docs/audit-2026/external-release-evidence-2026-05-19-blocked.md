# Audit 2026 external release evidence - blocked run

This is a retained evidence record for the 2026-05-19 remediation branch. It is
not a release approval. The final external release bundle did not complete
because the selected UMS backend checkout is private from the GitHub Actions
runner without `UMS_BACKEND_TOKEN`.

## Release candidate

- Flowforge branch: `audit-2026-critical-readiness`
- Flowforge commit with current PR evidence: `3b8fcf7`
- UMS backend repository/ref attempted in Actions: `nyimbi/ums@main`
- UMS backend commit verified locally: `cae102c91eda1553dfc234a87a16cc396cf51ea1`
- Date/time UTC: 2026-05-19
- Environment: local macOS sandbox plus GitHub Actions Ubuntu runners

## Passing evidence

- PR checks on `3b8fcf7` all passed:
  - `JTBD bundle lint`: run `26096687992`
  - `audit-2026` matrix: run `26096687970`
  - `browser-full-stack`: run `26096687890`
  - `flowforge end-to-end gate`: run `26096687920`
  - `generate-dom-baselines`: run `26096687973`
  - `audit-2026-sla-stress (nightly)`: skipped on pull request as expected
- Focused external workflow ratchet:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`
  - Result: `11 passed`
- Full audit ratchets:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026 -q --tb=short`
  - Result: `200 passed`
- Workflow lint:
  - `actionlint .github/workflows/audit-2026-release-external.yml`
  - Result: passed
- UMS parity against fresh local checkout:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend make audit-2026-ums-parity`
  - Result: `134 passed`
- External preflight with local UMS checkout and live Postgres URL:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/private/tmp/flowforge-ums-release-backend/backend FLOWFORGE_TEST_PG_URL=postgresql:///flowforge_release_codex_20260519_0506 uv run python scripts/audit_2026/check_external_release_preflight.py`
  - Result: passed with the caveat that browser execution is verified only by `make audit-2026-release-external`

## Blocked evidence

- Manual external workflow run: `26095402727`
- Workflow: `.github/workflows/audit-2026-release-external.yml`
- Inputs:
  - `backend_repository=nyimbi/ums`
  - `backend_ref=main`
- Result: failed before `make audit-2026-release-external`
- Failure point: `Checkout UMS backend without token`
- Failure message: `repository 'https://github.com/nyimbi/ums/' not found`
- Interpretation: the selected UMS backend is private from the GitHub Actions
  runner. `UMS_BACKEND_TOKEN` must be configured with read access to `nyimbi/ums`
  before this workflow can produce a complete retained release artifact.

## Not Yet Satisfied

- `make audit-2026-release-external` has not passed in GitHub Actions.
- No completed `audit-2026-release-external-evidence` artifact exists for this
  release candidate.
- Criterion 15 in `critical-system-gap-audit-2026-05-18.md` remains blocked.

## Next Required Action

Configure a purpose-specific repository secret:

```bash
test -n "${FLOWFORGE_UMS_READ_TOKEN:-}"
gh secret set UMS_BACKEND_TOKEN \
  --repo nyimbi/flowforge \
  --body "$FLOWFORGE_UMS_READ_TOKEN"
```

Then rerun:

```bash
gh workflow run audit-2026-release-external.yml \
  --repo nyimbi/flowforge \
  --ref audit-2026-critical-readiness \
  -f backend_repository=nyimbi/ums \
  -f backend_ref=main
```
