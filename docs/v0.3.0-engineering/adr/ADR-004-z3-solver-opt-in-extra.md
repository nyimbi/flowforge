# ADR-004 — z3-solver as opt-in runtime extra

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-09 |
| Wave | Pre-W0 |
| Related item | [improvements.md item 4](../../improvements.md#4-guard-aware-reachability-checker) |
| Drives | W4a acceptance |

## Context

Item 4 (guard-aware reachability checker) needs `z3-solver` at generation time. The CLI command `flowforge jtbd-generate` is invoked from various install profiles:

- Development (uses `[dependency-groups] dev` per `pyproject.toml:140`).
- Production CI (installs the published `flowforge-cli` package).
- Host applications running `flowforge regen-catalog` or similar maintenance tasks.

The current `pyproject.toml` declares `z3-solver>=4.13` only under `[dependency-groups] dev`. Shipping item 4 as a generator-time check naively would mean every `flowforge-cli` install pulls z3 — including hosts that never run reachability and don't want a 50 MB native dependency.

Two design questions:

1. **Required dep vs optional extra?** If required, every install pays the size and platform-availability cost. If optional, the generator must handle the missing-extra case.
2. **Version pinning?** z3 produces SAT counter-examples; different z3 versions can produce different counter-examples on identical input. Without a pin, two CI hosts on different z3 versions emit divergent reachability artifacts, breaking byte-identical regen.

## Decision

**`z3-solver` is an opt-in runtime extra with a hard version pin.**

### `pyproject.toml` change

```toml
[project.optional-dependencies]
reachability = [
    "z3-solver==4.13.4.0",
]
```

Hosts opt in via `pip install flowforge-cli[reachability]` or `uv pip install 'flowforge-cli[reachability]'`. `z3-solver` is **removed** from `[dependency-groups] dev` and replaced by `flowforge-cli[reachability]` in the dev group, so dev installs continue to get z3 transparently.

### Hard version pin

`z3-solver==4.13.4.0` (or the latest stable at W4a sprint start). Range pins (`>=4.13`) are insufficient: SAT solvers are deterministic per-version but not stable across versions. Two different z3 patch releases can produce structurally different (but logically equivalent) counter-examples for the same constraint.

### Generator behaviour when extra not installed

The `reachability` per-JTBD generator at `flowforge_cli/jtbd/generators/reachability.py`:

```python
def generate(bundle, jtbd) -> GeneratedFile:
    try:
        import z3  # noqa: F401
    except ImportError:
        return GeneratedFile(
            path=f"workflows/{jtbd.id}/reachability_skipped.txt",
            content=(
                "Reachability analysis skipped: z3-solver not installed.\n"
                "Install with: pip install 'flowforge-cli[reachability]'\n"
            ),
        )
    return _run_reachability(bundle, jtbd)
```

The placeholder file is part of the regen output, so its presence is a deterministic signal that the extra is missing. Hosts running CI with the extra installed produce `reachability.json`; hosts without the extra produce `reachability_skipped.txt`. Both are byte-identical across runs.

### Pre-upgrade-check

`flowforge pre-upgrade-check --check-pyproject` runs against the host's installed packages and emits a warning if the host's `pyproject.toml` references `z3-solver` outside the `[reachability]` extra (the most common drift mode).

### CI installs the extra

`scripts/check_all.sh` and `.github/workflows/audit-2026.yml` install `flowforge-cli[reachability]` so CI exercises the real reachability path, not the skipped path. The `reachability_skipped.txt` codepath is only present so hosts can opt out without breaking regen.

## Consequences

**Positive:**
- Hosts that don't want z3 don't pay for it.
- Hosts that opt in get deterministic reachability artifacts (pinned version).
- Generator stays single-codepath; the placeholder file is part of the regen output, so determinism is preserved either way.
- Migration from dev-group to extra is mechanical; existing dev installs continue to work after a `uv sync`.

**Negative:**
- z3 version bumps require coordinated updates across every host running reachability. Mitigation: bump z3 only at minor-version boundaries (`v0.3.0` → `v0.4.0`), with a documented baseline rebase of every `reachability.json`.
- Two CI environments with different `[reachability]` install states (one installed, one not) produce different regen outputs. Mitigation: `scripts/check_all.sh` documents the requirement; CI matrix tests both states to ensure the placeholder path stays byte-stable.
- Some Linux distributions ship z3 builds that conflict with the pip-installed `z3-solver`. Mitigation: documented in [`docs/release/v0.3.0-upgrade.md`](../../release/) when v0.3.0 ships.

**Neutral:**
- Hosts on Windows or macOS get z3 as a wheel; no native build required.

## Alternatives considered

1. **Hard runtime dep** — rejected; forces every install to pull z3 even for hosts that never run reachability.
2. **Range pin (`z3-solver>=4.13`)** — rejected; SAT counter-examples drift across patch versions.
3. **Vendor z3 in `flowforge-cli`** — rejected; z3 is large (~50 MB) and the cost of vendoring exceeds the benefit.
4. **Run reachability as a separate CLI tool with its own install** — rejected; complicates the user experience for what should be a generator output.
5. **Skip determinism (let counter-examples drift)** — rejected; violates Principle 1.

## Implementation notes

- Migration of z3 from `[dependency-groups] dev` to `flowforge-cli[reachability]` lands in W4a's first PR.
- The `reachability_skipped.txt` placeholder format is fixed; CI lint asserts the file content matches the documented template (no version drift in the placeholder text itself).
- Version-bump procedure: when bumping z3, regenerate every `reachability.json` against a known-good fixture; assert structural equivalence (set of unreachable transitions) even if the specific counter-examples differ; update the pin and rebase the fixture.

## References

- [improvements.md item 4](../../improvements.md#4-guard-aware-reachability-checker)
- [v0.3.0-engineering-plan.md §4](../../v0.3.0-engineering-plan.md) — pre-wave decisions
- [`pyproject.toml`](../../../pyproject.toml) — `[dependency-groups] dev` (current home of z3 declaration)
- z3-solver releases: <https://pypi.org/project/z3-solver/#history>
