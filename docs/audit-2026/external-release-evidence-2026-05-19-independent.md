# Audit 2026 external release evidence - independent Flowforge gate

This is the retained release evidence record for the independent Flowforge
external release gate on 2026-05-19.

## Release candidate

- Flowforge branch: `audit-2026-critical-readiness`
- Flowforge commit: `ab47aec095b0213e0f7cc9b9b2648d5f3c6c8ea7`
- Workflow run: `26098960312`
- Workflow job: `76744304141`
- Artifact: `audit-2026-release-external-evidence`
- Artifact id: `7084214569`
- Artifact SHA256 digest: `9d6d2c387310cef76a964c45aede24319f6cb4e4f6653c14831d6f9a00e3ab28`
- UMS parity requested: `false`
- UMS backend repository/ref, if requested: `nyimbi/ums@main`
- Date/time UTC: `2026-05-19T13:05:10Z`
- Environment: GitHub Actions `ubuntu-latest` with Postgres 16 service and
  Playwright Chromium.

## Passing evidence

- `make audit-2026-release-external`: passed.
- DOM visual regression: passed in Playwright Chromium with `24 passed`.
- Browser full-stack Playwright: passed in Playwright Chromium with `1 passed`.
- Real-key polish-copy sidecar gate: passed against
  `examples/insurance_claim/jtbd-bundle.json.overrides.json`.
- Live Postgres release checks: passed against disposable Postgres service with
  `4 passed`.
- Downstream UMS workflow-def parity: not requested for this independent
  Flowforge release gate. The UMS parity lane had already passed locally
  against fresh checkout `cae102c91eda1553dfc234a87a16cc396cf51ea1` with
  `134 passed`.

## Artifact contents verified

Downloaded to `/private/tmp/flowforge-external-release-26098960312` and
inspected after the run. The artifact contains:

- Generated run evidence:
  `docs/audit-2026/external-release-evidence-current.md`.
- Historical blocked-run evidence:
  `docs/audit-2026/external-release-evidence-2026-05-19-blocked.md`.
- Evidence template and runbook.
- Reviewed DOM baselines under
  `examples/insurance_claim/screenshots/**/*.dom.html`.
- Reviewed sidecar
  `examples/insurance_claim/jtbd-bundle.json.overrides.json`.

## Interpretation

This satisfies the final independent Flowforge external-release criterion:
browser DOM baselines, browser full-stack e2e, reviewed sidecar, and live
Postgres checks have passed together in a browser-capable release environment
without local skip flags. UMS parity remains an explicit downstream
certification lane, not a dependency for independent Flowforge release
qualification.
