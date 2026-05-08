# Publishing flowforge to PyPI

Strategic packages (15) are PyPI-publishable as of v0.1.0. Domain-jtbd
starter scaffolds (30) are NOT — they ship as in-repo workspace
members only.

## Strategic packages

| Package | Wheel name | Notes |
|---|---|---|
| flowforge-core | `flowforge` | top-level pkg name is `flowforge` (no suffix) |
| flowforge-fastapi | `flowforge_fastapi` | |
| flowforge-sqlalchemy | `flowforge_sqlalchemy` | |
| flowforge-tenancy | `flowforge_tenancy` | |
| flowforge-audit-pg | `flowforge_audit_pg` | |
| flowforge-outbox-pg | `flowforge_outbox_pg` | |
| flowforge-rbac-static | `flowforge_rbac_static` | |
| flowforge-rbac-spicedb | `flowforge_rbac_spicedb` | |
| flowforge-documents-s3 | `flowforge_documents_s3` | |
| flowforge-money | `flowforge_money` | |
| flowforge-signing-kms | `flowforge_signing_kms` | SECURITY-BREAKING in v0.1.0 — see SECURITY-NOTE.md |
| flowforge-notify-multichannel | `flowforge_notify_multichannel` | |
| flowforge-cli | `flowforge_cli` | console entry: `flowforge` |
| flowforge-jtbd | `flowforge_jtbd` | |
| flowforge-jtbd-hub | `flowforge_jtbd_hub` | |

## Pre-publish gate

Run from the repo root. Every check must be green before any release.

```bash
# 1. Quality gate — runs pytest + pyright + JS test/typecheck +
#    UMS-parity + cross-package integration. Exits 0 if green.
bash framework/scripts/check_all.sh

# 2. Security ratchets.
bash scripts/ci/ratchets/check.sh

# 3. Signoff trail (audit-2026 DELIBERATE-mode requirement).
uv run --project framework --with pyyaml \
	python scripts/ci/check_signoff.py --strict

# 4. Conformance suite.
uv run --project framework pytest framework/tests/conformance/ -v
```

## Build

`uv build` produces an sdist + wheel per package. Run per-package:

```bash
for pkg in flowforge-core flowforge-fastapi flowforge-sqlalchemy \
		flowforge-tenancy flowforge-audit-pg flowforge-outbox-pg \
		flowforge-rbac-static flowforge-rbac-spicedb flowforge-documents-s3 \
		flowforge-money flowforge-signing-kms flowforge-notify-multichannel \
		flowforge-cli flowforge-jtbd flowforge-jtbd-hub; do
	(cd framework/python/$pkg && uv build)
done
```

Outputs land in `framework/dist/`.

## Validate

```bash
uv run --project framework --with twine \
	python -m twine check framework/dist/*.whl framework/dist/*.tar.gz
```

Every artifact should report `PASSED` (no warnings). Common failure
modes:

- `long_description missing` → README.md not picked up. Confirm
  `readme = "README.md"` in the package's `pyproject.toml` and the
  README is non-empty.
- `Invalid distribution metadata: '../../LICENSE' is invalid for
  'license-file'` → license-files entry is using a parent-dir
  pattern. Each package must have its own `LICENSE` file in its
  directory; the framework-root `LICENSE` is copied per-package.
- `InvalidDistribution: METADATA-Version 2.4 not supported` → uv /
  hatchling version mismatch; refresh with `uv self update`.

## Publish

```bash
# Test PyPI first.
uv run --project framework --with twine \
	python -m twine upload --repository testpypi framework/dist/*

# Real PyPI after smoke-testing the testpypi install.
uv run --project framework --with twine \
	python -m twine upload framework/dist/*
```

Authentication is via `~/.pypirc` or the `TWINE_USERNAME` /
`TWINE_PASSWORD` env vars. Use a project-scoped API token, never a
personal account password.

## Version bumps

Versions live in each package's `pyproject.toml::project.version`.
Bump every shipping package together; the workspace deps in
`framework/pyproject.toml::[tool.uv.sources]` resolve from the
workspace during local dev, so no per-package dep version pin needs
to track in lockstep.

For SECURITY-BREAKING changes (e.g., E-34 SK-01), bump the minor
component and add a `[SECURITY-BREAKING]` entry to
`framework/CHANGELOG.md` plus a `SECURITY-NOTE.md` migration note.

## Tagging

After publishing, tag the release:

```bash
git tag -a v0.X.Y -m "v0.X.Y — <release theme>"
git push --follow-tags
```

The audit-2026 v0.1.0 release is documented end-to-end at
`framework/docs/audit-2026/close-out.md`.

## Stamping helpers

The `framework/scripts/finalize_pypi_metadata.py` script stamps the
PEP 621 PyPI metadata (license, authors, keywords, classifiers,
project URLs) onto every strategic package's `pyproject.toml`.
Idempotent (looks for the `# pypi-metadata-stamped` marker). Re-run
if you add a new strategic package — update
`STRATEGIC_PACKAGES` and `_PER_PKG_KEYWORDS` in the script first.

## What's intentionally NOT shipped

- 30 `flowforge-jtbd-*-starter` domain packages — workspace-only,
  `package = false` in their `pyproject.toml` per E-46 / F-5
  two-step rollout. They ship as starter scaffolds for embedding,
  not as installable libraries.
- 5 strategic-vertical jtbd content packages (insurance, healthcare,
  banking, gov, hr) — also workspace-only for now; flip to
  `package = true` per pkg as their content reviews complete.
- The framework root `framework/pyproject.toml` itself — it's the
  workspace orchestrator, not a publishable package.
