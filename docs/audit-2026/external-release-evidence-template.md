# Audit 2026 external release evidence

Use this template for each critical-system release qualification run. Store the
completed copy next to the release candidate notes or attach it to the release
approval record.

## Release candidate

- Flowforge commit:
- UMS parity requested:
- UMS backend repository/ref, if requested:
- Operator:
- Date/time UTC:
- Environment:

## Preconditions

- DOM baseline commit:
- DOM baseline generation workflow run URL:
- DOM baseline candidate artifact URL:
- `examples/*/screenshots/**/*.dom.html` reviewed by:
- `VISREG_ALLOW_SKIP` unset for release commands:
- `BROWSER_E2E_ALLOW_SKIP` unset for release commands:
- Reviewed sidecar commit/path:
- `make audit-2026-polish-copy-sidecar` result:
- Sidecar authoring workflow run URL, if sidecar was refreshed:
- Sidecar candidate artifact URL, if sidecar was refreshed:
- `examples/insurance_claim/jtbd-bundle.json.overrides.json` reviewed by:
- LLM provider/model recorded in sidecar:
- `prompt_sha256` recorded in sidecar:
- `uv run python -c "import anthropic"` result, if Anthropic SDK authoring was used:
- `uv run flowforge polish-copy --require-llm --commit` command output reviewed,
  if sidecar was refreshed:

## Commands / workflow evidence

- `make audit-2026-release-local` result:
- `make audit-2026-release-external-preflight` result:
- Preflight caveat acknowledged: preflight does not prove browser execution;
  browser proof is the `audit-2026-browser-e2e` result below.
- Manual workflow:
  - Workflow file: `.github/workflows/audit-2026-release-external.yml`
  - Workflow run URL:
  - Artifact URL:
  - Uploadable PyPI `dist/*` artifacts present in artifact:
  - PyPI artifact checksum manifest URL/path:
  - `make audit-2026-pypi-artifact-manifest` result:
  - `run_ums_parity` input:
  - `backend_repository` input:
  - `backend_ref` input:
- Focused browser workflow:
  - Workflow file: `.github/workflows/audit-2026-browser-e2e.yml`
  - Workflow run URL:
  - Artifact URL:
- `make audit-2026-release-external` result:

## Required passing evidence

- DOM visual regression:
- Browser full-stack Playwright:
- Reviewed polish-copy sidecar gate (`make audit-2026-polish-copy-sidecar`):
- PyPI publication artifacts (`make audit-2026-pypi-build-dist`):
- PyPI artifact checksum manifest reviewed:
- PyPI artifact checksum manifest verified against retained `dist/*` artifacts:
- PyPI artifact checksum manifest schema/version/package identities reviewed:
- Optional downstream UMS workflow-def parity, if requested:
- Live Postgres stale snapshot rejection:
- Live Postgres SKIP LOCKED outbox drain:
- Live Postgres interleaved-tenant audit verification:
- Live Postgres tenant/ordinal index plan:

## Residual risks / exceptions

- Exceptions granted:
- Follow-up ticket(s):
- Release approver:
