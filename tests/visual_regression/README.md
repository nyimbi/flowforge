# Visual regression CI gate

Project-level Playwright runner for the v0.3.0 W3 visual regression
gate (item 21 in `docs/improvements.md`). The contract for this suite
is fixed by **ADR-001** at `docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md`;
read it first.

## What this does

Two artifacts, two gates, two cadences:

| Artifact | Gate | Cadence | Make target |
|---|---|---|---|
| DOM snapshot (normalised HTML, byte-equal) | CI-blocking | per-PR smoke + nightly full | `audit-2026-visual-regression-dom` |
| Pixel screenshot (PNG, SSIM ≥ 0.98) | Advisory | nightly only | `audit-2026-visual-regression-ssim` |

The DOM-snapshot bytes are deterministic across Chromium minor versions
because they're a pure function of `form_spec.json` + `Step.tsx` (both
deterministic generator outputs) once the ADR-001 normalisation rules
are applied:

1. strip `data-react-*` attributes
2. collapse whitespace
3. sort the `class` token list alphabetically
4. sort element attributes alphabetically

Pixel bytes are not deterministic — font hinting, GPU compositing, and
antialiasing drift between Chromium releases — so they're advisory only.

## Layout

```
tests/visual_regression/
├── playwright.config.ts          # two projects: dom (gating), ssim (advisory)
├── package.json                  # @flowforge/visual-regression
├── tsconfig.json
├── harness/                      # local Vite server for generated examples
├── lib/
│   ├── page_catalog.ts           # (example, flavor, page, viewport) tuples
│   ├── dom_normalize.ts          # ADR-001 normalisation rules
│   └── ssim.ts                   # windowed mean-similarity (advisory)
├── tests/
│   ├── dom_snapshot.spec.ts      # CI-blocking DOM byte-equality
│   └── pixel_ssim.spec.ts        # advisory pixel SSIM
└── README.md
```

Baselines live alongside the example bundles, not under this directory:

```
examples/<example>/screenshots/
├── frontend/
│   ├── <page>.mobile.dom.html
│   ├── <page>.mobile.png
│   ├── <page>.tablet.dom.html
│   ├── <page>.tablet.png
│   ├── <page>.desktop.dom.html
│   └── <page>.desktop.png
└── frontend-admin/
    └── <page>.<viewport>.{dom.html,png}
```

## Running

The runner is wrapped by two shell scripts under `scripts/visual_regression/`:

```bash
# CI-gating: DOM bytes only, smoke (canonical example) per PR
bash scripts/visual_regression/run_dom_snapshots.sh smoke

# CI-gating: DOM bytes only, full suite (every example) — nightly
bash scripts/visual_regression/run_dom_snapshots.sh full

# Advisory: pixel SSIM, nightly
bash scripts/visual_regression/run_ssim.sh
```

The DOM wrapper is fail-closed by default. Missing Playwright packages,
missing harness dependencies, or missing checked-in DOM baselines fail
the command. Use `VISREG_ALLOW_SKIP=1` only while bootstrapping a local
checkout; CI and release gates must not set it.

On macOS, Playwright Chromium must run in a browser-capable process
context. If Chromium exits with
`MachPortRendezvousServer ... Permission denied`, the gate is being run
from a sandbox that blocks Chromium's Mach bootstrap registration. Run
the same command from an unsandboxed terminal, or from CI with browser
launch support. Do not set `VISREG_ALLOW_SKIP=1` for a release or
publish readiness gate.

Or via Make:

```bash
make audit-2026-visual-regression-dom    # CI per-PR (smoke); nightly (full)
make audit-2026-visual-regression-ssim   # nightly only
```

## Refreshing baselines

After an intentional template change (e.g. a Step.tsx layout edit, a
design-token theme bump), the baselines need to be regenerated:

```bash
cd tests/visual_regression
UPDATE_BASELINES=1 pnpm test
git add ../../examples/*/screenshots/
git commit -m "chore(visreg): refresh DOM + pixel baselines"
```

Per ADR-001 §"Implementation notes", baseline rebases also happen
weekly via a scheduled GitHub Action that opens a PR with new
baselines for reviewer judgement.

## Dev-server harness

The shell wrappers start `tests/visual_regression/harness/` automatically
when `VISREG_DEV_SERVER_URL` is unset. The harness is a small Vite app
that mounts the checked-in generated Next-style Step pages and generated
admin page components directly from `examples/*/generated/`.

Set `VISREG_DEV_SERVER_URL` only when you want to point Playwright at an
already-running host app. Otherwise, run the wrapper and let it manage
the local server lifecycle.

## See also

- `docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md` — binding contract
- `docs/improvements.md` item 21 — original proposal
- `docs/v0.3.0-engineering-plan.md` §7 W3 / §11 residual risk #1
- `tests/integration/README.md` — predecessor "Playwright runner deferral" entry
