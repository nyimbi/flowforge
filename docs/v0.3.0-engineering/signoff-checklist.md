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

## Wave W1 — Generation surface widening

```yaml
- item: W1-item-8
  title: "Bundle-derived OpenAPI 3.1 generator (per-bundle openapi.yaml)"
  wave: W1
  property: Capable
  worker: worker-openapi
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/openapi.py (NEW — per-bundle generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES paths declared)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/tests/test_openapi_generator.py (NEW)"
      - "examples/insurance_claim/generated/openapi.yaml (NEW — 107 lines)"
      - "examples/building-permit/generated/openapi.yaml (NEW — 426 lines)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_openapi_generator.py — 14 tests green (operation tagging, x-audit-topics, x-permissions, deterministic key ordering, validation-derived examples, byte-identical regen)"
    pre_deploy_checks:
      - "bash scripts/check_all.sh step 8 — green (regen-diff against examples/*/generated/ exercises the new openapi.yaml emission for both insurance_claim and building-permit)"
      - "uv run pytest python/flowforge-cli/tests/test_openapi_generator.py — green"
    determinism_proof: |
      Generation is a pure function of the normalized bundle: operation
      key order is fixed (tags → summary → operationId → requestBody →
      responses → x-audit-topics → x-permissions); request-body
      examples are derived from data_capture validation ranges with no
      randomisation; YAML serialization uses sort_keys=False but each
      dict is constructed in canonical order. Two regens against the
      same bundle yield byte-identical YAML — pinned by
      scripts/check_all.sh step 8 against
      examples/insurance_claim/generated/openapi.yaml and
      examples/building-permit/generated/openapi.yaml.
    cross_runtime_parity_proof: |
      No expression evaluator surface is touched; openapi.yaml
      consumes only static bundle metadata. Invariant 5 stays green
      without fixture v2 churn (item 13 ships fixture v2 for an
      orthogonal reason).
    rollback_plan: |
      git revert <sha>; the generator is purely additive (new module +
      registration in _PER_BUNDLE_GENERATORS). No schema migration, no
      runtime port change, no public API change to flowforge-core.
      Hosts that consume openapi.yaml continue to work against the
      revert-prior absence of the file.
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

- item: W1-item-13
  title: "Real form generation behind bundle.project.frontend.form_renderer flag (skeleton | real)"
  wave: W1
  property: [Functional, Beautiful]
  worker: worker-realform
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py (NEW — JtbdFrontend model + FormRendererMode literal; JtbdProject.frontend optional field)"
      - "python/flowforge-core/src/flowforge/dsl/schema/jtbd-1.0.schema.json (project.properties.frontend block added — additive)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/normalize.py (form_renderer threads from bundle.project.frontend through NormalizedBundle)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/frontend.py (dual-path emission: skeleton retained byte-identical, real path emits FormRenderer + PII + aria-describedby)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2 (dual-path Jinja conditional)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (project.frontend.form_renderer declared)"
      - "python/flowforge-cli/tests/test_form_renderer_flag.py (NEW — 6 tests)"
      - "examples/insurance_claim/jtbd-bundle.json (declares project.frontend.form_renderer = 'real')"
      - "examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx (real-path output now baselined)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_form_renderer_flag.py — 6 tests green (default skeleton path byte-identical against pre-W1 emission; real path emits FormRenderer import + PII fields + aria wiring; switching the flag is the only delta; both paths regen deterministically)"
      - "tests/cross_runtime/test_expr_parity.py — green against expr_parity_v2.json (250 cases, conditional tag covers show_if shapes)"
    pre_deploy_checks:
      - "bash scripts/check_all.sh step 8 — green (insurance_claim regenerates byte-identical against the locked real-path baseline; building-permit + hiring-pipeline regenerate byte-identical against the unchanged skeleton path)"
      - "uv run pytest python/flowforge-cli/tests/test_form_renderer_flag.py — green"
      - "make audit-2026-cross-runtime — green (fixture v2, 250 cases)"
    determinism_proof: |
      The dual-path emission is gated on a single Jinja conditional
      (`{% if form_renderer == 'real' %}`); both branches are
      generator-pure (no clock, no randomness, no environment lookup).
      Skeleton-path output is byte-identical to pre-W1 emission for
      every bundle that does not opt in (verified via building-permit
      + hiring-pipeline regen-diff). Real-path output is byte-identical
      across regens (verified via insurance_claim regen-diff against
      the locked baseline). Pinned by scripts/check_all.sh step 8 on
      both flag values.
    cross_runtime_parity_proof: |
      The real-form path's `show_if` shape — `{var: "context.<edge_id>"}`
      — uses the same `var` operator already exercised by `branch`.
      No new operator enters the cross-runtime registry. Fixture v2
      (250 cases, 50 `conditional`-tagged) extends coverage to the
      `show_if`-shaped fragments the W1 real-form path emits;
      `tests/cross_runtime/test_expr_parity.py` is repointed at
      fixture v2 (lines 23, 33-35, 50-63 edited per Pre-mortem
      Scenario 2). Invariant 5 stays green; legacy
      `expr_parity_200.json` retained until W3 per plan §11.1.
    rollback_plan: |
      git revert <sha>; the JtbdFrontend block is optional
      (`frontend: JtbdFrontend | None = None`), the schema addition is
      additive, the template's real-path branch is gated on
      `form_renderer == "real"`. Reverting restores skeleton-only
      emission for every bundle. The example bundle update for
      insurance_claim (sets `form_renderer = "real"`) reverts
      transparently — the bundle's `frontend` block becomes a no-op
      under reverted code that ignores it. No schema migration, no
      DB change, no host API surface change.
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

- item: W1-item-19
  title: "State-machine diagram emission (per-JTBD diagram.mmd; README mermaid embed)"
  wave: W1
  property: [Beautiful, Functional]
  worker: worker-diagram
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/diagram.py (NEW — per-JTBD generator, mermaid stateDiagram-v2 source)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/readme.py (mermaid embed for the synthesised diagram)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/README.md.j2 (mermaid block added)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_JTBD_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES paths declared)"
      - "python/flowforge-cli/tests/test_jtbd_diagram_generator.py (NEW — 30 tests)"
      - "examples/insurance_claim/generated/workflows/claim_intake/diagram.mmd (NEW)"
      - "examples/building-permit/generated/workflows/{field_inspection,permit_decision,permit_intake,permit_issuance,plan_review}/diagram.mmd (NEW × 5)"
      - "examples/insurance_claim/generated/README.md, examples/building-permit/generated/README.md (mermaid embed)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_jtbd_diagram_generator.py — 30 tests green (swimlane palette assignment, terminal-kind colouring, compensation lane styling, edge-case priority glyphs, SLA-budget annotation, byte-identical regen across runs)"
    pre_deploy_checks:
      - "bash scripts/check_all.sh step 8 — green (insurance_claim + building-permit regenerate byte-identical with diagram.mmd in tree)"
      - "uv run pytest python/flowforge-cli/tests/test_jtbd_diagram_generator.py — green"
    determinism_proof: |
      The generator is deliberately .mmd-source-only — no SVG
      rendering via mermaid-cli (which would break byte-identical
      regen across mermaid-cli versions per Principle 1 of
      docs/v0.3.0-engineering-plan). State / transition / classDef
      ordering is sorted; swimlane-to-palette assignment is by the
      role's position in the sorted-unique-swimlane list; terminal
      colouring is keyed on `state.kind` only; edge-case priority
      glyphs are picked from a fixed mapping. Two regens against the
      same bundle yield byte-identical .mmd — pinned by
      scripts/check_all.sh step 8 against
      examples/insurance_claim/generated/workflows/claim_intake/diagram.mmd
      and the five examples/building-permit/generated/workflows/*/diagram.mmd.
    cross_runtime_parity_proof: |
      Generator does not touch the expression evaluator. No fixture
      churn required.
    rollback_plan: |
      git revert <sha>; the generator is purely additive (new module
      + registration in _PER_JTBD_GENERATORS + README template
      mermaid block). The README mermaid block is an additive
      `## Workflow diagram` section and reverts transparently. No
      schema migration, no runtime port change.
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

- item: W1-fixture-v2
  title: "Cross-runtime expression parity fixture v2 (250 cases, conditional tag added)"
  wave: W1
  property: Reliable
  worker: worker-realform
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "tests/cross_runtime/fixtures/expr_parity_v2.json (NEW — 250 cases: 200 base + 50 conditional-tagged)"
      - "tests/cross_runtime/_build_fixture_v2.py (NEW — deterministic fixture builder)"
      - "tests/cross_runtime/test_expr_parity.py (FIXTURE_PATH at :23, count assertion at :33-35, required-tags set at :50-63 per Pre-mortem Scenario 2 / plan §11.1)"
    test_path: "tests/cross_runtime/test_expr_parity.py"
    acceptance_criterion: |
      The 50 new conditional-tagged cases exercise the show_if-shaped
      fragments the W1 real-form path emits in the dual-path
      Step.tsx.j2 template. Both Python (flowforge.expr) and TS
      (@flowforge/renderer) evaluators agree byte-for-byte on every
      case; the conditional-tag set is included in the
      required-coverage assertion at :50-63 so a future PR cannot
      drop it without explicit override.
    pre_deploy_checks:
      - "uv run pytest tests/cross_runtime/test_expr_parity.py -v — passed (250 cases)"
      - "make audit-2026-cross-runtime — passed"
      - "(cd js && pnpm -F @flowforge/integration-tests test expr-parity) — green against fixture v2"
    rollback_plan: |
      git revert <sha>; the legacy expr_parity_200.json is retained
      in-tree per plan §11.1 (until W3). Reverting fixture v2 reverts
      test_expr_parity.py to the 200-case fixture; the new ratchet
      `no_unparried_expr_in_step_template` would then fail because
      Step.tsx.j2's real-path branch references expression-shaped
      tokens — this is the intended interlock so the fixture cannot
      drift behind the template.
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

- item: W1-ratchet-no-unparried-expr
  title: "Ratchet — no_unparried_expr_in_step_template (Pre-mortem Scenario 2 mitigation)"
  wave: W1
  property: Reliable
  worker: worker-realform
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "scripts/ci/ratchets/no_unparried_expr_in_step_template.sh (NEW — greps Step.tsx.j2 for JSON-DSL expr tokens; asserts fixture v2 has ≥ 50 conditional-tagged cases when any are present)"
      - "scripts/ci/ratchets/no_unparried_expr_in_step_template_baseline.txt (NEW — empty baseline; legitimate exceptions require security-team review)"
      - "scripts/ci/ratchets/check.sh (added to RATCHETS=() — 4 → 5 ratchets)"
    acceptance_criterion: |
      `scripts/ci/ratchets/check.sh` reports 5/5 ratchets pass.
      Removing fixture v2 or reducing its conditional-tag count
      below 50 fails the ratchet loud, with a message pointing the
      contributor at fixture v2 + the PR-template "Touches expr
      evaluator?" checkbox.
    pre_deploy_checks:
      - "bash scripts/ci/ratchets/check.sh — 5/5 PASS"
      - "make audit-2026-ratchets — green"
    rollback_plan: |
      git revert <sha>; revert removes the new ratchet script + its
      baseline + the RATCHETS=() entry. Other ratchets unaffected.
      Reverting also reverts the cross-runtime fixture v2 row so the
      interlock remains atomic per the plan §11.1.
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
```

---

## Wave W2 — Observability backbone + reliability artefacts

```yaml
- item: W2-item-7
  title: "Backup/restore drill artefact (restore_runbook generator + make restore-drill target)"
  wave: W2
  property: Reliable
  worker: worker-runbook
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/restore_runbook.py (NEW — per-bundle generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/restore_runbook.md.j2 (NEW)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (registered restore_runbook entry)"
      - "python/flowforge-cli/tests/test_restore_runbook_generator.py (NEW — 16 unit tests)"
      - "tests/integration/python/tests/test_restore_drill.py (NEW — testcontainers Postgres dump→drop→restore→verify integration test)"
      - "Makefile (NEW targets: restore-drill, audit-2026-restore-drill)"
      - "examples/insurance_claim/generated/docs/ops/insurance_claim_demo/restore-runbook.md (NEW — regenerated)"
      - "examples/building-permit/generated/docs/ops/building_permit/restore-runbook.md (NEW — regenerated)"
      - "examples/hiring-pipeline/generated/docs/ops/hiring_pipeline/restore-runbook.md (NEW — regenerated)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_restore_runbook_generator.py — green (16 tests covering output shape, FK ordering, idempotency tolerance, determinism, fixture-registry roundtrip, pipeline integration)"
      - "tests/integration/python/tests/test_restore_drill.py — skips cleanly when Postgres + testcontainers + docker daemon unavailable; green end-to-end against testcontainers Postgres when all three are present"
    pre_deploy_checks:
      - "uv run pytest python/flowforge-cli/tests/ — green (283 tests)"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
      - "scripts/check_all.sh step 8 (deterministic regen) — byte-identical for all 3 examples (insurance_claim, building-permit, hiring-pipeline) including the new docs/ops/<bundle>/restore-runbook.md output"
      - "make restore-drill — runs the testcontainers drill (PG required); skips with clear reason otherwise"
    determinism_proof: |
      The runbook is a pure-functional render: ``_table_view`` sorts by
      jtbd.id, ``_audit_topic_view`` defers to bundle.all_audit_topics
      (already sorted+deduplicated by normalize), and the template
      receives only those derived views plus the project metadata.
      Two regens against the same bundle produce byte-identical output;
      verified per-example in
      ``test_deterministic_output_{insurance_claim,building_permit,hiring_pipeline}``.
      Item 6's per-JTBD ``<table>_idempotency_keys`` table is
      gracefully tolerated: when ``project.idempotency_ttl_hours``
      is absent on the normalized bundle (sibling worker-idempotency
      not landed yet) the runbook still emits cleanly with entity
      tables only — exercised by
      ``test_idempotency_gracefully_tolerated_when_attr_missing``.
    rollback_plan: |
      git revert <sha>; the runbook generator + template + Makefile
      target + tests all unwire atomically. The generated
      ``docs/ops/<bundle>/restore-runbook.md`` files in
      ``examples/*/generated/`` come back out via the next regen.
      Restore drill is opt-in: hosts that haven't wired it suffer no
      regression on revert.
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

- item: W2-item-12
  title: "OpenTelemetry by construction (TracingPort + HistogramMetricsPort + flowforge-otel adapter + spans in templates)"
  wave: W2
  property: [Capable, Reliable]
  worker: worker-otel
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-core/src/flowforge/ports/tracing.py (NEW — TracingPort Protocol + STANDARD_SPAN_NAMES + STANDARD_SPAN_ATTRIBUTES)"
      - "python/flowforge-core/src/flowforge/ports/metrics.py (HistogramMetricsPort extension)"
      - "python/flowforge-core/src/flowforge/ports/__init__.py (re-exports)"
      - "python/flowforge-core/src/flowforge/config.py (tracing slot wired alongside the existing 14 ports)"
      - "python/flowforge-core/src/flowforge/testing/port_fakes.py (InMemoryTracingPort + InMemoryHistogramMetricsPort)"
      - "python/flowforge-core/src/flowforge/testing/__init__.py (re-exports)"
      - "python/flowforge-core/tests/unit/test_ports_protocols.py (TracingPort + HistogramMetricsPort assertions)"
      - "python/flowforge-otel/ (NEW — workspace member; src/flowforge_otel/{__init__,errors,metrics_adapter,tracing_adapter,wiring}.py)"
      - "python/flowforge-otel/tests/test_{tracing,metrics}_adapter.py + test_wiring.py (NEW)"
      - "python/flowforge-otel/pyproject.toml + README.md + CHANGELOG.md + LICENSE (NEW)"
      - "pyproject.toml (workspace + dependencies + opentelemetry-api/sdk dev-deps; flowforge-otel as workspace member)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/domain_service.py.j2 (OTel span wrap on fire/effect dispatch)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/domain_router.py.j2 (OTel span wrap on event POST)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/workflow_adapter.py.j2 (OTel span wrap on audit-append)"
      - "examples/{insurance_claim,building-permit}/generated/backend/src/<pkg>/services/*.py + routers/*.py + adapters/*.py (regenerated with span wraps)"
      - "tests/integration/python/tests/test_otel_spans_in_generated_app.py (NEW — span sequence assertion against the in-memory fake)"
      - "tests/observability/promql/v0_3_0_w2_item_12_otel.yml (NEW — alert rules for the standard meter set)"
    acceptance_tests:
      - "python/flowforge-otel/tests/ — 10 tests green (tracing adapter, metrics adapter, wiring helper)"
      - "python/flowforge-core/tests/unit/test_ports_protocols.py — green (TracingPort, HistogramMetricsPort, runtime_checkable)"
      - "tests/integration/python/tests/test_otel_spans_in_generated_app.py — green (end-to-end span sequence)"
      - "promtool check rules tests/observability/promql/v0_3_0_w2_item_12_otel.yml — green (when promtool installed)"
    pre_deploy_checks:
      - "uv run pytest python/flowforge-otel/tests/ -q — green (10 tests)"
      - "uv run pyright python/flowforge-otel/src --pythonversion 3.11 — 0 errors, 0 warnings"
      - "scripts/check_all.sh step 8 — byte-identical regen for all 3 examples (insurance_claim + building-permit + hiring-pipeline) including the new OTel span wraps in domain_service/router/workflow_adapter outputs"
    determinism_proof: |
      The templates emit literal span-wrap blocks gated by static
      Jinja conditionals; no clock, no randomness, no environment
      lookup. Two regens against the same bundle produce
      byte-identical service/router/adapter Python — pinned by
      step 8 against examples/insurance_claim/generated/backend/src/
      insurance_claim_demo/services/claim_intake_service.py and
      every analogous file in building-permit + hiring-pipeline.
    cross_runtime_parity_proof: |
      Generator does not touch the expression evaluator. Span name
      / attribute constants are Python-only; the TS sibling does
      not enter the cross-runtime fixture. Invariant 5 stays green
      against fixture v2 (250 cases).
    rollback_plan: |
      git revert <sha>; the TracingPort + HistogramMetricsPort
      additions are additive (Protocols, no breaking change to the
      existing 14 ports). The flowforge-otel package can be
      removed from the workspace independently. Templates fall
      back to no-op spans when the in-memory fake is wired.
      Reverting restores pre-W2 service/router/adapter emission.
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

- item: W2-item-6
  title: "Router-level idempotency keys (header enforcement + per-tenant table + invariant 11)"
  wave: W2
  property: Reliable
  worker: worker-idempotency
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/idempotency.py (NEW — per-JTBD generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/idempotency.py.j2 (NEW)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/db_migration_idempotency_keys.py.j2 (NEW — chained per-JTBD migration with UniqueConstraint)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/db_migration.py (chains the idempotency-keys migration after the entity migration)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/domain_router.py.j2 (Idempotency-Key header + check_idempotency_key + record_idempotency_response wiring)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/domain_service.py.j2 (dedupe call on the service-side fire path)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/normalize.py (project.idempotency.ttl_hours threading)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_JTBD_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES paths declared)"
      - "python/flowforge-cli/tests/test_jtbd_idempotency.py (NEW)"
      - "scripts/ci/ratchets/no_idempotency_bypass.sh (NEW — generator-side gate enforcement)"
      - "scripts/ci/ratchets/no_idempotency_bypass_baseline.txt (NEW — empty baseline)"
      - "scripts/ci/ratchets/check.sh (added to RATCHETS=() — 5 → 6 ratchets)"
      - "tests/conformance/test_arch_invariants.py (NEW invariant 11 + docstring count fix to 11)"
      - "examples/insurance_claim/generated/backend/src/insurance_claim_demo/claim_intake/idempotency.py (NEW — regenerated)"
      - "examples/insurance_claim/generated/backend/migrations/versions/<rev>_create_claim_intake_idempotency_keys.py (NEW)"
      - "examples/building-permit/generated/backend/migrations/versions/<rev>_create_<jtbd>_idempotency_keys.py × 5 (NEW per JTBD)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_jtbd_idempotency.py — green (helper emission, migration UniqueConstraint, header gate, TTL threading, byte-determinism)"
      - "tests/conformance/test_arch_invariants.py::test_invariant_11_idempotency_key_uniqueness — green"
      - "scripts/ci/ratchets/check.sh — 6/6 ratchets PASS (incl. no_idempotency_bypass)"
    pre_deploy_checks:
      - "make audit-2026-conformance — 11 invariants pass (was 10)"
      - "make audit-2026-ratchets — 6 ratchets pass (was 5)"
      - "scripts/check_all.sh step 8 — byte-identical regen for all 3 examples including the new idempotency helpers + chained migrations"
      - "uv run pytest python/flowforge-cli/tests/ -q — 300 tests green"
    determinism_proof: |
      The per-JTBD idempotency helper renders from a Jinja template
      with the bundle-supplied TTL hours substituted in. The chained
      migration emits with a deterministic revision id
      (`sha256(package + jtbd_id + "_idempotency_keys")[:12]`) so
      two regens against the same bundle yield byte-identical
      migrations + helpers. Pinned via
      `test_idempotency_helper_byte_deterministic` and
      `test_chained_migration_revision_id_deterministic`.
    cross_runtime_parity_proof: |
      The header gate is Python-only; no expression evaluator
      surface is touched. Invariant 5 stays green without fixture
      churn.
    rollback_plan: |
      git revert <sha>; the idempotency generator is additive (new
      module + new template + chained migration emission gated on
      `project.idempotency.ttl_hours` presence). The router /
      service template gates the helper imports behind the same
      flag so reverting restores the pre-W2 router shape. The
      ratchet baseline file remains on disk after revert; nothing
      references it. Reverting also reverts invariant 11 and the
      docstring count back to 10.
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

- item: W2-invariant-11
  title: "Conformance invariant 11 — idempotency-key uniqueness"
  wave: W2
  property: Reliable
  marker: "@invariant_p1"
  worker: worker-idempotency
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "tests/conformance/test_arch_invariants.py (NEW invariant 11 + header docstring fix to 11)"
    test_path: "tests/conformance/test_arch_invariants.py::test_invariant_11_idempotency_key_uniqueness"
    acceptance_criterion: |
      For every JTBD in a bundle that opts into idempotency, the
      chained migration carries a UniqueConstraint over
      (tenant_id, idempotency_key); a SQLite round-trip insert with
      the same (tenant_id, idempotency_key) pair raises
      IntegrityError; and the generated idempotency helper threads
      the bundle-configured TTL through to its IDEMPOTENCY_TTL_HOURS
      literal (default 24h when project.idempotency.ttl_hours is
      unset). Also asserts the router template wires the
      check_idempotency_key + record_idempotency_response helpers.
    pre_deploy_checks:
      - "uv run pytest tests/conformance/test_arch_invariants.py::test_invariant_11_idempotency_key_uniqueness -v — passed"
      - "make audit-2026-conformance — 11 invariants passed"
    rollback_plan: |
      git revert <sha>; the test is purely additive — it imports
      the flowforge_cli.jtbd idempotency generator already
      exercised by the test_jtbd_idempotency unit suite, then
      asserts on the normalised output. Removing it leaves
      invariants 1-10 green.
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

- item: W2-ratchet-no-idempotency-bypass
  title: "Ratchet — no_idempotency_bypass (invariant 11 generator-side enforcement)"
  wave: W2
  property: Reliable
  worker: worker-idempotency
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "scripts/ci/ratchets/no_idempotency_bypass.sh (NEW — greps domain_router.py.j2 + every checked-in <jtbd>_router.py)"
      - "scripts/ci/ratchets/no_idempotency_bypass_baseline.txt (NEW — empty baseline; legitimate exceptions require security/architecture review)"
      - "scripts/ci/ratchets/check.sh (added to RATCHETS=() — 5 → 6 ratchets)"
    acceptance_criterion: |
      `scripts/ci/ratchets/check.sh` reports 6/6 ratchets pass.
      Removing the Idempotency-Key header parameter, the
      check_idempotency_key import, the record_idempotency_response
      call, the HTTP_400_BAD_REQUEST or HTTP_409_CONFLICT status
      codes from the router template (or any of the regenerated
      example router files) fails the ratchet loud, with a message
      pointing the contributor at item 6's helper module.
    pre_deploy_checks:
      - "bash scripts/ci/ratchets/check.sh — 6/6 PASS"
      - "make audit-2026-ratchets — green"
    rollback_plan: |
      git revert <sha>; revert removes the new ratchet script + its
      baseline + the RATCHETS=() entry. Other ratchets unaffected.
      Reverting also reverts the chained idempotency-keys migration
      emission so the gate has nothing to enforce.
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

- item: W2-item-15
  title: "Tenant-scoped admin console (frontend_admin generator + per-bundle React app)"
  wave: W2
  property: [Functional, Capable]
  worker: worker-admin
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/frontend_admin.py (NEW — per-bundle generator, 15 file emission)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_admin/ (NEW directory — package.json, tsconfig, vite.config, index.html, README, src/{main,App,api,permissions}.tsx + src/pages/{InstanceBrowser,AuditLogViewer,SagaPanel,PermissionsHistory,OutboxQueue,RlsLog}.tsx Jinja templates)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES paths declared)"
      - "python/flowforge-cli/tests/test_frontend_admin_generator.py (NEW)"
      - "examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/ (NEW SPA tree)"
      - "examples/building-permit/generated/frontend-admin/building_permit/ (NEW SPA tree)"
      - "examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/ (NEW SPA tree — example tree first checked in this wave)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_frontend_admin_generator.py — green (file set, sorted-jtbd traversal, admin-permissions synthesis, byte-determinism, fixture-registry roundtrip)"
    pre_deploy_checks:
      - "scripts/check_all.sh step 8 — byte-identical regen for all 3 examples including the new frontend-admin/<package>/ trees"
      - "uv run pytest python/flowforge-cli/tests/test_frontend_admin_generator.py -q — green"
    determinism_proof: |
      Every emitted file is rendered from a Jinja template with
      sorted iteration over JTBDs (sorted by jtbd.id) and
      sorted-unique synthesis of the admin.<jtbd>.{read,compensate,
      outbox.retry,grant} permission set. Two regens against the
      same bundle produce byte-identical output — pinned per
      example via the W2 closeout regen-diff loop.
    cross_runtime_parity_proof: |
      Generator does not touch the expression evaluator. The
      admin SPA's API client uses string keys only (no DSL). No
      fixture churn required.
    rollback_plan: |
      git revert <sha>; the generator is purely additive (new
      module + new templates directory + registration in
      _PER_BUNDLE_GENERATORS). The generated frontend-admin/
      trees regenerate as empty after revert — hosts that adopted
      the SPA see it disappear on next regen but their existing
      deployment is unaffected (the SPA is deployed in isolation
      behind a separate ingress / auth proxy, not coupled to the
      customer-facing Next.js app).
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

- item: W2-item-16
  title: "Closed analytics-event taxonomy (analytics_taxonomy generator + new AnalyticsPort)"
  wave: W2
  property: [Functional, Capable]
  worker: worker-analytics
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-core/src/flowforge/ports/analytics.py (NEW — AnalyticsPort Protocol)"
      - "python/flowforge-core/src/flowforge/ports/__init__.py (re-export)"
      - "python/flowforge-core/src/flowforge/config.py (analytics slot wired alongside the existing 14 ports)"
      - "python/flowforge-core/src/flowforge/testing/port_fakes.py (InMemoryAnalyticsPort)"
      - "python/flowforge-core/src/flowforge/testing/__init__.py (re-export)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/analytics_taxonomy.py (NEW — per-bundle generator emitting two files)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/analytics_taxonomy.py.j2 (NEW)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/analytics_taxonomy.ts.j2 (NEW)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES paths declared)"
      - "python/flowforge-cli/tests/test_analytics_taxonomy.py (NEW)"
      - "examples/insurance_claim/generated/backend/src/insurance_claim_demo/analytics.py (NEW — regenerated)"
      - "examples/insurance_claim/generated/frontend/src/insurance_claim_demo/analytics.ts (NEW — regenerated)"
      - "examples/building-permit/generated/backend/src/building_permit/analytics.py (NEW)"
      - "examples/building-permit/generated/frontend/src/building_permit/analytics.ts (NEW)"
      - "examples/hiring-pipeline/generated/backend/src/hiring_pipeline/analytics.py (NEW)"
      - "examples/hiring-pipeline/generated/frontend/src/hiring_pipeline/analytics.ts (NEW)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_analytics_taxonomy.py — green (event enumeration shape, sorted iteration, byte-determinism, parallel Python/TS taxonomy agreement)"
      - "python/flowforge-core/tests/unit/test_ports_protocols.py — green (AnalyticsPort runtime_checkable + InMemoryAnalyticsPort track behaviour)"
    pre_deploy_checks:
      - "scripts/check_all.sh step 8 — byte-identical regen for all 3 examples including the new analytics.py + analytics.ts"
      - "uv run pytest python/flowforge-cli/tests/test_analytics_taxonomy.py -q — green"
    determinism_proof: |
      The generator sorts JTBDs by id and iterates the closed
      LIFECYCLE_SUFFIXES tuple in fixed order, so two regens
      against the same bundle yield byte-identical Python StrEnum
      and TS string-literal type. The Python and TS sides emit
      the same set of (member, event) pairs — the parallel-output
      assertion in test_analytics_taxonomy verifies the closure
      contract holds across runtimes.
    cross_runtime_parity_proof: |
      The TS-side closed enum is a string-literal type — no
      runtime expression evaluator surface is touched. Invariant 5
      stays green without fixture churn.
    rollback_plan: |
      git revert <sha>; the AnalyticsPort + InMemoryAnalyticsPort
      additions are additive (new Protocol, new fake). The
      generator is purely additive (new module + 2 templates +
      registration in _PER_BUNDLE_GENERATORS). Reverting removes
      the analytics.py + analytics.ts files on next regen; hosts
      that wired AnalyticsPort fall back to no-op tracking until
      they wire their own enum.
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
```

---

*This file is the v0.3.0-engineering equivalent of
`docs/audit-2026/signoff-checklist.md`. Treated as a living doc — wave
sections are appended as W1..W4b land.*
