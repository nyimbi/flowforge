# v0.3.0-engineering — Per-wave Signoff Checklist

**Purpose**: Per-item signoff trail for the 22 generation-pipeline
improvements landed across waves W0..W4b per
`docs/v0.3.0-engineering-plan.md`. Mirrors the pattern of
`docs/audit-2026/signoff-checklist.md` but scoped to the
v0.3.0-engineering track.

**CI gate**: each wave's verification target (e.g.
`make audit-2026-conformance`, `bash scripts/check_all.sh`) must report
green before the wave's row(s) here are signed.

**Roles**:
- Architecture lead: Nyimbi Odero
- QA lead: Nyimbi Odero
- Release manager: Nyimbi Odero
- Per-wave DRI: TBD per wave at sprint start

> **Approval pattern: single-stakeholder.** Reviewed and signed off by a
> single accountable owner (Nyimbi Odero) acting in all roles
> concurrently. The pattern preserves the evidence trail and CI gate
> while consolidating the human approval step. Additional reviewers may
> co-sign existing rows by appending to the relevant `*_signoff` blocks.

---

## Wave W0 — Reliability close-outs

```yaml
- item: W0-item-1
  title: "Migration safety analyzer (CLI + per-bundle generator + ratchet + pre-upgrade-check subcheck)"
  wave: W0
  property: Reliable
  worker: worker-migration-safety
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/commands/migration_safety.py (NEW — Typer subcommand)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/migration_safety.py (NEW — per-bundle generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (NEW — fixture-coverage primer)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/migration_safety.md.j2 (NEW)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/main.py (wired migration-safety subcommand)"
      - "python/flowforge-cli/src/flowforge_cli/commands/pre_upgrade_check.py (subcheck added)"
      - "python/flowforge-cli/tests/test_migration_safety_cli.py (NEW)"
      - "python/flowforge-cli/tests/test_migration_safety_generator.py (NEW)"
      - "python/flowforge-cli/tests/test_pre_upgrade_check.py (extended with migration-safety subcheck)"
      - "scripts/ci/ratchets/migration_safety_baseline.txt (NEW — baseline of currently-unsafe migrations)"
      - "examples/insurance_claim/generated/backend/migrations/safety/ (regenerated)"
      - "examples/building-permit/generated/backend/migrations/safety/ (regenerated)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_migration_safety_cli.py — green"
      - "python/flowforge-cli/tests/test_migration_safety_generator.py — green"
      - "python/flowforge-cli/tests/test_pre_upgrade_check.py — green (migration-safety subcheck row)"
    pre_deploy_checks:
      - "bash scripts/check_all.sh — green (regen-diff step 8 passes for all examples; the migrations/safety/ subtree is now part of the byte-identical baseline)"
      - "uv run pytest python/flowforge-cli/tests/ — green"
    determinism_proof: |
      The generator is a static AST-walk over the emitted alembic file
      and a read-only template render. Two regens against the same
      bundle produce byte-identical safety reports — pinned by the
      regen-diff gate at scripts/check_all.sh step 8.
    rollback_plan: |
      git revert <sha>; the generator is purely additive (new module +
      new Typer subcommand + new ratchet baseline). No schema migration,
      no public API change to flowforge-core. The ratchet baseline file
      remains on disk after revert; nothing references it.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD

- item: W0-item-2
  title: "Compensation synthesis (transforms + workflow_adapter template + new per-JTBD generator)"
  wave: W0
  property: [Reliable, Capable]
  worker: worker-compensation
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/transforms.py (derive_states adds singleton compensated terminal_fail; derive_transitions emits LIFO-paired compensate transitions)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/workflow_adapter.py.j2 (gated CompensationWorker import + register_compensations entrypoint)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/compensation_handlers.py (NEW — per-JTBD generator, silent when no compensate edge_case)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/compensation_handlers.py.j2 (NEW)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_JTBD_GENERATORS)"
      - "python/flowforge-cli/tests/test_jtbd_compensation_synthesis.py (NEW)"
      - "examples/insurance_claim/jtbd-bundle.json (declares fraud_detected compensate edge_case)"
      - "examples/insurance_claim/generated/ (regenerated — adds compensation_handlers.py + paired effects in workflow_def.json)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_jtbd_compensation_synthesis.py — green (transforms, generator emission gate, byte-determinism, fixture-registry coverage)"
      - "tests/conformance/test_arch_invariants.py::test_invariant_10_compensation_symmetry — green"
    pre_deploy_checks:
      - "bash scripts/check_all.sh — green (regen-diff against examples/insurance_claim/generated/ exercises the new compensation paths)"
      - "uv run pytest python/flowforge-cli/tests/test_jtbd_compensation_synthesis.py — green"
    determinism_proof: |
      The synthesiser is a pure function of the parsed bundle: forward-
      walk the synthesised transitions in encounter order, collect
      compensable effects, reverse for LIFO, attach to each compensate
      transition. Two pipeline runs against the same bundle produce
      byte-identical output — pinned both by the dedicated
      test_compensate_pipeline_is_byte_deterministic and by the
      project-wide regen-diff gate.
    cross_runtime_parity_proof: |
      Compensate transitions guard on `{var: "context.<edge_id>"}` —
      the same expression shape `branch` already uses. No new operator
      enters the cross-runtime fixture; invariant 5 stays green
      without fixture v2 churn.
    rollback_plan: |
      git revert <sha>; the synthesiser is opt-in (only fires when a
      JTBD declares handle: "compensate"), the workflow_adapter template
      gates the new import behind _compensate_transitions, and the
      per-JTBD generator returns None for non-compensating JTBDs. Revert
      restores the previous "manual_review trampoline" behaviour for
      compensate edges. No DB migration. Hosts that adopted
      register_compensations(worker) revert to host-supplied compensation
      maps as before.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD

- item: W0-invariant-10
  title: "Conformance invariant 10 — compensation symmetry"
  wave: W0
  property: Reliable
  marker: "@invariant_p1"
  worker: worker-closeout
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "tests/conformance/test_arch_invariants.py (NEW invariant 10 + docstring count fix)"
      - "tests/conformance/fixtures/compensation_symmetry/jtbd-bundle.json (NEW)"
    test_path: "tests/conformance/test_arch_invariants.py::test_invariant_10_compensation_symmetry"
    acceptance_criterion: |
      For every JTBD declaring an edge_case with handle: "compensate"
      and at least one effects: [{kind: "create_entity"}] forward
      transition, the synthesised compensate transition MUST contain a
      paired compensate_delete saga step in matching LIFO order. Also
      asserts that _PER_JTBD_GENERATORS[workflow_adapter] emits the
      CompensationWorker import gate when compensations are present.
    pre_deploy_checks:
      - "uv run pytest tests/conformance/test_arch_invariants.py::test_invariant_10_compensation_symmetry -v — passed"
      - "make audit-2026-conformance — 10 invariants passed"
    rollback_plan: |
      git revert <sha>; the test is purely additive — it imports the
      flowforge_cli.jtbd synthesiser already exercised by the
      compensation_synthesis unit suite, then asserts on the
      normalized output. Removing it leaves invariants 1-9 green.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD

- item: W0-docstring-fix
  title: "Stale docstring fix in tests/conformance/test_arch_invariants.py header"
  wave: W0
  property: Quality
  worker: worker-closeout
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "tests/conformance/test_arch_invariants.py (header — count drift fix; bundled with invariant 10)"
    note: |
      The original header described "8 architectural invariants" since
      audit-2026 close-out. The E-74 follow-up landed invariant 9
      without updating the header; W0 adds invariant 10. The header now
      reads "10 architectural invariants" and references both the
      audit-2026 and v0.3.0 signoff checklists. Bundled with invariant
      10 per the W0 closeout protocol so a single edit covers both.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-09
    commit_sha: TBD
```

---

*This file is the v0.3.0-engineering equivalent of
`docs/audit-2026/signoff-checklist.md`. Treated as a living doc — wave
sections are appended as W1..W4b land.*
