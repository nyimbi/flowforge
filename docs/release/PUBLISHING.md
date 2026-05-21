# Publishing flowforge to PyPI

Shipping packages (16) are PyPI-publishable as of v0.1.0. Domain JTBD
workspace packages (30) are NOT — they remain in-repo workspace members
only until package-level review flips their `[tool.uv] package` flag.

## Shipping packages

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
| flowforge-otel | `flowforge_otel` | OpenTelemetry metrics/tracing adapter |
| flowforge-cli | `flowforge_cli` | console entry: `flowforge` |
| flowforge-jtbd | `flowforge_jtbd` | |
| flowforge-jtbd-hub | `flowforge_jtbd_hub` | |

## Pre-publish gate

Run from the repo root. Every check must be green before any release.

```bash
# 1. Quality gate — runs pytest + pyright + JS test/typecheck +
#    standalone-safe regen, visual DOM, and cross-package integration.
#    Downstream UMS parity is skipped unless BACKEND_ROOT is available.
bash scripts/check_all.sh

# 2. Security ratchets.
bash scripts/ci/ratchets/check.sh

# 3. Signoff trail (audit-2026 DELIBERATE-mode requirement).
uv run --with pyyaml \
	python scripts/ci/check_signoff.py --strict

# 4. Conformance suite.
uv run pytest tests/conformance/ -v

# 5. PyPI artifact gate — builds all 16 shipping packages, verifies
#    exactly one wheel and one sdist per package, checks that typed
#    packages include `py.typed` in their wheels, verifies declared
#    license files are present in wheel/sdist payloads, verifies built
#    wheel and sdist metadata keep internal Flowforge dependencies bounded
#    and limited to shipping distributions, runs `twine check`,
#    smoke-installs every shipping wheel, imports every shipping package,
#    and runs the flowforge-cli console entrypoint.
make audit-2026-pypi-build
```

## Build

`make audit-2026-pypi-build` is the canonical release gate. It discovers
shipping packages from the workspace metadata, builds each package, requires
exactly one wheel and one sdist per package, verifies PEP 561 `py.typed`
markers are present in typed package wheels, verifies wheel `METADATA` /
sdist `PKG-INFO` `Name` / `Version` fields match the shipping package and
artifact filename, verifies each wheel and sdist contains the declared
`LICENSE` file, verifies the wheel's own
`.dist-info/METADATA` and top-level sdist `PKG-INFO` `Requires-Dist` metadata
keep internal Flowforge dependencies on the exact `>=0.1.0,<0.2.0`
compatibility bound, with no extra internal dependency specifiers, and limited
to shipping distributions, checks every wheel/sdist with `twine`, then
installs every shipping wheel from the built artifacts into a clean venv,
imports every shipping package, and runs `flowforge --help`.

`uv build` produces an sdist + wheel per package. Do not maintain a separate
manual package list for release builds; the gate discovers shipping packages
from `[tool.uv.workspace].members` and each package's `[tool.uv] package`
flag through `scripts/audit_2026/package_sets.py`.

```bash
make audit-2026-pypi-build
```

By default, the gate writes artifacts to the temporary readiness directory
reported at the end of the run. To produce the uploadable publication
artifact set in the repository `dist/` directory, run the same smoke script
with an explicit publication-staging flag:

```bash
uv run python scripts/audit_2026/pypi_build_smoke.py \
	--dist-dir dist \
	--allow-repo-dist
```

This deletes and recreates the repository `dist/` directory, then leaves the
validated wheel and sdist artifacts there for the `twine` commands below.

## Validate

```bash
uv run --with twine \
	python -m twine check dist/*.whl dist/*.tar.gz

python -m venv /tmp/flowforge-cli-wheel-smoke
/tmp/flowforge-cli-wheel-smoke/bin/python -m pip install \
	--force-reinstall dist/*.whl
/tmp/flowforge-cli-wheel-smoke/bin/python -c \
	"import importlib; [importlib.import_module(m) for m in (
	'flowforge', 'flowforge_fastapi', 'flowforge_sqlalchemy',
	'flowforge_tenancy', 'flowforge_audit_pg', 'flowforge_outbox_pg',
	'flowforge_rbac_static', 'flowforge_rbac_spicedb',
	'flowforge_documents_s3', 'flowforge_money', 'flowforge_signing_kms',
	'flowforge_notify_multichannel', 'flowforge_otel', 'flowforge_cli',
	'flowforge_jtbd', 'flowforge_jtbd_hub')]"
/tmp/flowforge-cli-wheel-smoke/bin/flowforge --help >/dev/null
```

Every artifact should report `PASSED` (no warnings), and the clean
wheel smoke must import every shipping package and print CLI help without
`ModuleNotFoundError`.
Common failure modes:

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
uv run --with twine \
	python -m twine upload --repository testpypi dist/*

# Real PyPI after smoke-testing the testpypi install.
uv run --with twine \
	python -m twine upload dist/*
```

Authentication is via `~/.pypirc` or the `TWINE_USERNAME` /
`TWINE_PASSWORD` env vars. Use a project-scoped API token, never a
personal account password.

## Version bumps

Versions live in each package's `pyproject.toml::project.version`.
Bump every shipping package together; the workspace deps in
`pyproject.toml::[tool.uv.sources]` resolve from the
workspace during local dev, so no per-package dep version pin needs
to track in lockstep.

For SECURITY-BREAKING changes (e.g., E-34 SK-01), bump the minor
component and add a `[SECURITY-BREAKING]` entry to
`CHANGELOG.md` plus a `SECURITY-NOTE.md` migration note.

## Tagging

After publishing, tag the release:

```bash
git tag -a v0.X.Y -m "v0.X.Y — <release theme>"
git push --follow-tags
```

The audit-2026 v0.1.0 release is documented end-to-end at
`docs/audit-2026/close-out.md`.

## Stamping helpers

The `scripts/finalize_pypi_metadata.py` script stamps the
PEP 621 PyPI metadata (license, authors, keywords, classifiers,
project URLs) onto the current shipping package set. Idempotent
(looks for the `# pypi-metadata-stamped` marker). Re-run if a new
package flips to `[tool.uv] package = true`, then update the script's
package metadata map if the ratchet reports missing PyPI metadata.

## What's intentionally NOT shipped

- 30 `flowforge-jtbd-*` domain packages, excluding `flowforge-jtbd-hub`,
  are workspace-only with `package = false` in their `pyproject.toml` per
  E-46 / F-5 two-step rollout. Most are starter scaffolds for embedding,
  not installable libraries.
- Five of those workspace-only domain packages (insurance, healthcare,
  banking, gov, hr) are strategic domain-content candidates. They keep
  their original names rather than `-starter`, but remain not publishable
  until named SME signoff, publishable packaging, and release review are
  complete.
- The repository root `pyproject.toml` itself — it's the
  workspace orchestrator, not a publishable package.
