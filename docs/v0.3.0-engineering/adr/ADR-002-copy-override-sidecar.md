# ADR-002 — Copy override sidecar schema

| | |
|---|---|
| Status | Accepted |
| Date | 2026-05-09 |
| Wave | Pre-W0 |
| Related item | [improvements.md item 22](../../improvements.md#22-last-mile-copy-polish-via-opt-in-llm) |
| Drives | W4b acceptance |

## Context

Item 22 introduces `flowforge polish-copy --tone <profile>`, an offline LLM pass over user-facing strings (field labels, helper text, button labels, error messages, notification templates). Two design questions need decisions before W4b opens:

1. **Where does the schema live?** The naive answer is "extend `JtbdBundle` with an `overrides` field". This pollutes the canonical content-addressable surface (`JtbdBundle.model_config = ConfigDict(extra='forbid')`) — every consumer of `JtbdBundle` would need to opt out of overrides handling, and `spec_hash` either changes (breaking content-addressing) or excludes overrides (creating a parallel address space).

2. **How does the override file persist?** Embedding into the bundle means overrides participate in `spec_hash`; if the LLM call's output is non-deterministic across runs, the same logical bundle with different override generations produces different hashes. This violates Principle 1.

Both questions point at the same answer: keep overrides **out of the canonical bundle**.

## Decision

**Sidecar file pattern.** A copy-override file lives next to the bundle on disk, named `<bundle_path>.overrides.json`. The schema lives in `flowforge_cli` (the consumer), not in `flowforge_jtbd` (the canonical model).

### Schema (`flowforge_cli.jtbd.overrides.JtbdCopyOverrides`)

```python
from pydantic import BaseModel, ConfigDict
from typing import Literal

class JtbdCopyOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["1.0"] = "1.0"
    tone_profile: Literal[
        "formal-professional",
        "friendly-direct",
        "regulator-compliant",
    ]
    strings: dict[str, str]
    # Metadata (audit trail; excluded from regen-diff hash):
    generated_at: str | None = None      # ISO-8601
    generator_version: str | None = None  # "flowforge polish-copy v0.3.0"
```

### String key convention

```
<jtbd_id>.field.<field_id>.label
<jtbd_id>.field.<field_id>.helper_text
<jtbd_id>.button.<event>.text
<jtbd_id>.notification.<topic>.template
<jtbd_id>.error.<code>.message
```

Missing keys fall back to canonical bundle values. Keys not in the convention are rejected by the Pydantic validator (covered by `extra='forbid'` on inner string keys would be ideal, but `dict[str, str]` doesn't support per-key forbidding; instead, a separate `_validate_string_keys` `@model_validator` enforces the namespace pattern).

### Persistence

- File: `<bundle_path>.overrides.json` (co-located with the bundle).
- `flowforge polish-copy --commit` writes the file; `flowforge polish-copy --dry-run` prints a diff vs the existing file.
- The file is **a committed artifact**. CI fails if `flowforge polish-copy` is invoked and the resulting file is uncommitted (`git status --porcelain` check).

### Lookup precedence

1. Explicit `--overrides <path>` flag on `flowforge jtbd-generate`.
2. Co-located file: `<bundle_path>.overrides.json`.
3. None: use canonical strings.

Two examples nested in the same parent directory cannot cross-pollinate because each sidecar is named after its own bundle path.

### Application point

Overrides apply at **`form_spec` and `frontend` generation time**, not at canonical bundle level. The canonical `JtbdBundle.model_validate()` never sees the overrides; only the generators do.

### `spec_hash` invariance

The override file does **not** participate in `JtbdSpec.compute_hash()`. The canonical bundle's `spec_hash` is unchanged whether overrides exist or not.

The `(bundle, sidecar)` tuple **does** participate in the regen-diff hash (`scripts/check_all.sh` step 8). This catches sidecar drift at PR time without affecting `spec_hash` semantics.

## Consequences

**Positive:**
- Canonical `JtbdBundle` and `JtbdSpec` are unchanged. No schema-version bump for v0.3.0.
- `spec_hash` invariant preserved.
- LLM non-determinism is contained: the LLM call produces the sidecar once, the sidecar is committed, and regen reads from the committed file deterministically.
- The sidecar is a discoverable, diffable artifact in the host repo — operators can read it without running the CLI.

**Negative:**
- Two files now travel together (bundle + sidecar). Hosts moving bundles must move both. Mitigation: `flowforge new` and `flowforge add-jtbd` automatically copy the sidecar; documentation calls out the pairing.
- Sidecar can drift from the bundle (e.g. a field renamed in the bundle but not in the sidecar). Mitigation: lint rule that fails CI if a sidecar key doesn't resolve to a real bundle field.
- `flowforge polish-copy` requires the bundle file to exist on disk; cannot operate on in-memory dicts. Acceptable for an authoring CLI.

**Neutral:**
- Hosts can author overrides by hand without running the LLM (`flowforge polish-copy` is one producer; the file format is the source of truth).

## Alternatives considered

1. **Embed `overrides` in `JtbdBundle`** — rejected. Mutates the canonical content-addressable surface; either changes `spec_hash` semantics or creates a parallel address space.
2. **Embed `overrides` in `JtbdSpec` per-JTBD** — rejected. Same issue, plus duplicates strings across JTBDs that share a tone profile.
3. **Apply overrides at form_spec emit time only (not reachable from `JtbdBundle.model_validate`)** — accepted; this is the chosen path. Overrides are a generation-time concern, never a spec concern.
4. **Store overrides in a database** — rejected; adds runtime infrastructure for an authoring concern.
5. **Inline LLM call in the regen pipeline (no sidecar)** — rejected. Violates Principle 1 (determinism).

## Implementation notes

- Schema location: `python/flowforge-cli/src/flowforge_cli/jtbd/overrides.py`.
- Consumer: `python/flowforge-cli/src/flowforge_cli/jtbd/generators/form_spec.py` and `frontend.py` import the loader.
- Loader: `flowforge_cli.jtbd.overrides.load_sidecar(bundle_path: Path) -> JtbdCopyOverrides | None`.
- CI gate: `tests/v0_3_0/test_polish_copy_committed_overrides.py` — after `flowforge polish-copy --commit` completes, `git status --porcelain` must be empty.
- Lint rule: a sidecar key like `claim_intake.field.foo.label` must resolve to a real `data_capture` field (`foo`) on a real JTBD (`claim_intake`).

## References

- [improvements.md item 22](../../improvements.md#22-last-mile-copy-polish-via-opt-in-llm)
- [v0.3.0-engineering-plan.md §4](../../v0.3.0-engineering-plan.md) — pre-wave decisions
- [`python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py`](../../../python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py) — `JtbdBundle` (unchanged)
- [`docs/jtbd-grammar.md`](../../jtbd-grammar.md) — bundle wire format
