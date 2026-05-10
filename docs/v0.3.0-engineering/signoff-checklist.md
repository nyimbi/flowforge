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

## Wave W3 — Multi-frontend, diff, lineage, theming, visual regression

```yaml
- item: W3-item-10
  title: "Bundle-diff CLI with deploy-safety classes (additive / requires-coordination / breaking)"
  wave: W3
  property: Reliable
  worker: worker-bundlediff
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/commands/bundle_diff.py (NEW — Typer subcommand + categorisation engine + JSON/HTML/text renderers)"
      - "python/flowforge-cli/src/flowforge_cli/main.py (wired bundle-diff subcommand)"
      - "python/flowforge-cli/tests/test_bundle_diff.py (NEW — 38 tests covering every categorisation rule + CLI wiring + insurance_claim W0→W1 integration)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_bundle_diff.py — green (38 passed)"
    pre_deploy_checks:
      - "uv run pyright python/flowforge-cli/src/flowforge_cli/commands/bundle_diff.py python/flowforge-cli/src/flowforge_cli/main.py — 0 errors"
      - "uv run pyright python/flowforge-cli/tests/test_bundle_diff.py — 0 errors"
      - "uv run pytest tests/conformance/ -q — 11/11 passed"
      - "bash scripts/ci/ratchets/check.sh — 6/6 passed"
      - "uv run pytest python/flowforge-cli/tests/test_bundle_diff.py -q — 38/38 passed"
      - "git diff --stat examples/ — empty (CLI is operational, doesn't emit into examples; regen-diff stays byte-identical by construction)"
    determinism_proof: |
      The categorisation engine sorts JTBDs / fields / edge_cases by id,
      sorts shared.permissions and shared.roles before comparing as
      sets, and the report is sorted with key (kind_rank, path,
      category) — kind_rank pins the most-severe class first.
      `render_json` calls `json.dumps(..., sort_keys=True, indent=2)`;
      `render_html` iterates the sorted change list and embeds JSON
      detail with the same `sort_keys=True`. A parametrised determinism
      test (`test_renderers_are_deterministic`) runs each renderer twice
      and asserts byte-identical output.
    rollback_plan: |
      git revert <sha>; the CLI is purely additive — new module + new
      Typer subcommand + new test file + one-line wire-up in
      flowforge_cli/main.py. No schema migration, no public API change
      to flowforge-core, no example files emitted. Reverting removes the
      `flowforge bundle-diff` command from the CLI surface; nothing else
      depends on it.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W3-item-9
  title: "Multi-frontend emission (CLI + Slack + email per-bundle generators)"
  wave: W3
  property: Capable
  worker: worker-multifrontend
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/frontend_cli.py (NEW — Typer CLI client per-bundle generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/frontend_slack.py (NEW — slash-command + interactive-message adapter generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/frontend_email.py (NEW — reply-to-trigger email adapter generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_cli/ (NEW directory — package skeleton + per-JTBD command templates)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_slack/ (NEW directory — Bolt-style adapter skeleton)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_email/ (NEW directory — IMAP-trigger adapter skeleton)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES paths declared)"
      - "python/flowforge-cli/tests/test_frontend_cli_generator.py (NEW)"
      - "python/flowforge-cli/tests/test_frontend_slack_generator.py (NEW)"
      - "python/flowforge-cli/tests/test_frontend_email_generator.py (NEW)"
      - "examples/insurance_claim/generated/frontend-cli/ (NEW per-bundle tree)"
      - "examples/insurance_claim/generated/frontend-slack/ (NEW per-bundle tree)"
      - "examples/insurance_claim/generated/frontend-email/ (NEW per-bundle tree)"
      - "examples/building-permit/generated/frontend-cli/ (NEW per-bundle tree)"
      - "examples/building-permit/generated/frontend-slack/ (NEW per-bundle tree)"
      - "examples/building-permit/generated/frontend-email/ (NEW per-bundle tree)"
      - "examples/hiring-pipeline/generated/frontend-cli/ (NEW per-bundle tree)"
      - "examples/hiring-pipeline/generated/frontend-slack/ (NEW per-bundle tree)"
      - "examples/hiring-pipeline/generated/frontend-email/ (NEW per-bundle tree)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_frontend_cli_generator.py — green"
      - "python/flowforge-cli/tests/test_frontend_slack_generator.py — green"
      - "python/flowforge-cli/tests/test_frontend_email_generator.py — green"
    pre_deploy_checks:
      - "uv run pytest python/flowforge-cli/tests/ -q — 443/443 green"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
      - "scripts/check_all.sh step 8 — byte-identical regen for all 3 examples × 2 form_renderer values (6/6 via scripts/ci/regen_flag_flip.sh) including the new frontend-cli/, frontend-slack/, frontend-email/ trees"
    determinism_proof: |
      Every emitted file is rendered from a Jinja template with sorted
      iteration over JTBDs (`sorted(bundle.jtbds, key=lambda j: j.id)`).
      Per-JTBD command / handler files iterate the same canonical key
      order used by the existing frontend generator. The CLI client's
      Typer subcommand registration is a sorted-by-id loop; the Slack
      adapter's slash-command registration is sorted by JTBD id; the
      email adapter's IMAP routing table is sorted by JTBD id. Two
      regens against the same bundle produce byte-identical output —
      pinned per example via the W3 closeout regen-diff loop.
    cross_runtime_parity_proof: |
      Generators do not touch the expression evaluator. The CLI uses
      Typer; the Slack adapter uses Slack Block Kit; the email adapter
      uses the Python IMAP client — none consume the JSON-DSL. No
      fixture churn required.
    rollback_plan: |
      git revert <sha>; the three generators are purely additive (new
      modules + new templates + 3 _PER_BUNDLE_GENERATORS registrations).
      The generated frontend-cli/, frontend-slack/, frontend-email/
      trees regenerate as empty after revert — hosts that adopted any
      of them see the tree disappear on next regen but their existing
      deployment is unaffected (each adapter is deployed in isolation
      behind its own ingress / process boundary).
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W3-item-11
  title: "Data lineage / provenance graph (lineage.json per-bundle generator)"
  wave: W3
  property: [Capable, Reliable]
  worker: worker-lineage
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/lineage.py (NEW — per-bundle generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES paths declared)"
      - "python/flowforge-cli/tests/test_lineage_generator.py (NEW)"
      - "examples/insurance_claim/generated/lineage.json (NEW)"
      - "examples/building-permit/generated/lineage.json (NEW)"
      - "examples/hiring-pipeline/generated/lineage.json (NEW)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_lineage_generator.py — green (field traversal, PII redaction-strategy synthesis, role-exposure closure, sorted JSON keys, byte-identical regen)"
    pre_deploy_checks:
      - "uv run pytest python/flowforge-cli/tests/test_lineage_generator.py -q — green"
      - "scripts/check_all.sh step 8 — byte-identical regen for all 3 examples including the new lineage.json"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
    determinism_proof: |
      The generator walks `data_capture` fields per JTBD in
      `(jtbd_id, field_id)` sorted order, computes the closure of
      `(field → service → orm_column → audit_topic → outbox_envelope)`
      stages, and emits `json.dumps(..., sort_keys=True, indent=2)`.
      Two regens against the same bundle produce byte-identical
      lineage.json — pinned by scripts/check_all.sh step 8 against
      examples/insurance_claim/generated/lineage.json,
      examples/building-permit/generated/lineage.json, and
      examples/hiring-pipeline/generated/lineage.json.
    cross_runtime_parity_proof: |
      Generator does not touch the expression evaluator. lineage.json
      is consumed by external compliance tooling; no DSL surface.
      No fixture churn required.
    rollback_plan: |
      git revert <sha>; the generator is purely additive (new module
      + registration in _PER_BUNDLE_GENERATORS). The generated
      lineage.json files regenerate as empty after revert; downstream
      compliance tooling that consumes lineage.json gracefully handles
      its absence (degrades to "no provenance graph available").
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W3-item-18
  title: "Design-token-driven theming (bundle.project.design + design_tokens generator)"
  wave: W3
  property: Beautiful
  worker: worker-tokens
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py (NEW JtbdProjectDesign model; JtbdProject.design optional field)"
      - "python/flowforge-core/src/flowforge/dsl/schema/jtbd-1.0.schema.json (project.properties.design block added — additive)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/normalize.py (design tokens thread from bundle.project.design through NormalizedBundle)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/design_tokens.py (NEW — per-bundle generator emitting CSS + Tailwind config + TS theme)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/design_tokens/ (NEW directory — design_tokens.css.j2 + tailwind.config.ts.j2 + theme.ts.j2)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2 (real-path imports design_tokens.css)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_admin/src/main.tsx.j2 (imports design_tokens.css)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (project.design.* declared)"
      - "python/flowforge-cli/tests/test_design_tokens.py (NEW)"
      - "python/flowforge-cli/tests/test_frontend_admin_generator.py (extended for design-tokens import assertion)"
      - "examples/insurance_claim/generated/frontend/src/insurance_claim_demo/{design_tokens.css,theme.ts} (NEW)"
      - "examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/{src/design_tokens.css,src/theme.ts,tailwind.config.ts} (NEW)"
      - "examples/building-permit/generated/frontend/src/building_permit/{design_tokens.css,theme.ts} (NEW)"
      - "examples/building-permit/generated/frontend-admin/building_permit/{src/design_tokens.css,src/theme.ts,tailwind.config.ts} (NEW)"
      - "examples/hiring-pipeline/generated/frontend/src/hiring_pipeline/{design_tokens.css,theme.ts} (NEW)"
      - "examples/hiring-pipeline/generated/frontend-admin/hiring_pipeline/{src/design_tokens.css,src/theme.ts,tailwind.config.ts} (NEW)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_design_tokens.py — green (CSS variable emission, Tailwind extension shape, TS Theme typing, sorted token order, byte-determinism)"
      - "python/flowforge-cli/tests/test_frontend_admin_generator.py — green (admin SPA main.tsx imports design_tokens.css)"
    pre_deploy_checks:
      - "uv run pytest python/flowforge-cli/tests/ -q — 443/443 green"
      - "scripts/check_all.sh step 8 — byte-identical regen for all 3 examples × 2 form_renderer values (6/6 via scripts/ci/regen_flag_flip.sh) including the new design_tokens.css + tailwind.config.ts + theme.ts trio in both frontend/ and frontend-admin/ trees"
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS (incl. no_design_token_hardcode)"
    determinism_proof: |
      The generator iterates the closed token surface
      (primary, accent, neutral, font_family, density, radius_scale)
      in fixed order; tokens that the bundle does not override fall
      back to the canonical default constant (matched against the
      pre-W3 visual identity so existing examples regenerate
      byte-identical). CSS variable emission is sorted alphabetically;
      Tailwind extension keys are sorted; the TS Theme type is
      structurally typed against the closed token surface. Two regens
      against the same bundle yield byte-identical output for all
      three target files.
    cross_runtime_parity_proof: |
      Generator does not touch the expression evaluator. Tokens are
      static metadata rendered into CSS / TypeScript; no DSL surface.
      No fixture churn required.
    rollback_plan: |
      git revert <sha>; the JtbdProjectDesign block is optional
      (`design: JtbdProjectDesign | None = None`), the schema addition
      is additive, the generator is gated on the bundle declaring at
      least one design field. Reverting removes the design-tokens
      trio from both frontend/ and frontend-admin/ trees on next
      regen; templates fall back to the legacy hard-coded tokens. The
      `no_design_token_hardcode` ratchet would also need reverting in
      lockstep (the legacy hard-coded tokens trip the ratchet
      otherwise).
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W3-item-21
  title: "Visual regression CI gate (DOM-snapshot primary, SSIM advisory) per ADR-001"
  wave: W3
  property: [Beautiful, Reliable]
  worker: worker-visregression
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "tests/visual_regression/ (NEW directory — Playwright config, helpers, specs, ADR-001 normaliser)"
      - "tests/visual_regression/README.md (NEW — pnpm-install blocker + unblock procedure)"
      - "scripts/visual_regression/run_dom_snapshots.sh (NEW — DOM-snapshot CI-gating runner; smoke per-PR / full nightly)"
      - "scripts/visual_regression/run_ssim.sh (NEW — pixel SSIM advisory runner; nightly only)"
      - "scripts/check_all.sh (step 9 added between regen-diff step 8 and UMS parity, renumbering subsequent steps)"
      - "Makefile (audit-2026-visual-regression-dom + audit-2026-visual-regression-ssim targets)"
      - "examples/insurance_claim/screenshots/ (NEW directory — baseline catalog stub)"
      - "examples/building-permit/screenshots/ (NEW directory — baseline catalog stub)"
      - "examples/hiring-pipeline/screenshots/ (NEW directory — baseline catalog stub)"
    acceptance_tests:
      - "tests/visual_regression/ ADR-001 normaliser — 5/5 unit tests pass (strip data-react-*, collapse whitespace, sort class tokens, sort attributes, idempotence)"
    pre_deploy_checks:
      - "make audit-2026-visual-regression-dom — exits 0 with [SKIP] reason: tests/visual_regression/node_modules missing — pnpm install blocked on the pre-existing pnpm-ignored-builds issue (the wrapper detects missing prerequisites and skips with a human-readable reason)"
      - "make audit-2026-visual-regression-ssim — exits 0 with [SKIP] reason (same blocker)"
      - "scripts/check_all.sh step 9 — exits 0 with [SKIP] reason"
    determinism_proof: |
      DOM-snapshot byte-equality is the CI-gating contract per ADR-001.
      The four normalisation rules (strip `data-react-*`, collapse
      whitespace, sort `class` tokens alphabetically, sort attributes
      alphabetically) cancel every known drift source across Chromium
      minor versions. The SSIM-pixel runner is advisory-only with an
      SSIM ≥ 0.98 threshold per ADR-001; runs nightly via
      `audit-2026-visual-regression-ssim`, never per-PR.
    cross_runtime_parity_proof: |
      Visual regression runs against generated frontend output, not
      the expression evaluator. No fixture churn.
    rollback_plan: |
      git revert <sha>; the runner + Make targets + check_all.sh
      step 9 + screenshots/ baselines are purely additive. Reverting
      removes the gate; nothing depends on it. Hosts that started
      using the runner fall back to no per-PR visual-regression CI
      until they re-adopt.
  follow_ups:
    - "pnpm-install blocker: once `pnpm approve-builds` is run for the workspace, baseline files land in a follow-up PR with no further changes to the runner."
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header). DOM-snapshot CI gate green-by-skip-with-clear-reason; baselines and full per-page assertions land in follow-up once pnpm-install is unblocked."
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W3-ratchet-no-design-token-hardcode
  title: "Ratchet — no_design_token_hardcode (item 18 generator-side enforcement)"
  wave: W3
  property: Beautiful
  worker: worker-tokens
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "scripts/ci/ratchets/no_design_token_hardcode.sh (NEW — greps frontend templates + every checked-in examples/*/generated/frontend*/ tree for naked hex / rgb()/rgba()/hsl() / hard-coded font-family / radius literals outside the design-tokens helper module)"
      - "scripts/ci/ratchets/no_design_token_hardcode_baseline.txt (NEW — empty baseline; legitimate exceptions require security/UX review)"
      - "scripts/ci/ratchets/check.sh (added to RATCHETS=() — 6 → 7 ratchets)"
    acceptance_criterion: |
      `scripts/ci/ratchets/check.sh` reports 7/7 ratchets pass.
      Reintroducing a naked `#3b82f6`-style hex into Step.tsx.j2 or
      a regenerated example file (without listing it in the baseline)
      fails the ratchet loud and points the contributor at the
      design-tokens helper module.
    pre_deploy_checks:
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS"
      - "make audit-2026-ratchets — green"
    rollback_plan: |
      git revert <sha>; revert removes the new ratchet script + its
      baseline + the RATCHETS=() entry. Other ratchets unaffected.
      Reverting also implicitly accepts re-introducing hard-coded
      tokens; the design-tokens generator (item 18) would then need
      to be reverted in lockstep to keep the visual identity coherent.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W3-fixture-retirement
  title: "Cross-runtime fixture v1 retirement (expr_parity_200.json deleted; v2 canonical)"
  wave: W3
  property: Reliable
  worker: worker-visregression
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "tests/cross_runtime/fixtures/expr_parity_200.json (DELETED — superseded by expr_parity_v2.json's 200-case base layer)"
      - "tests/cross_runtime/_build_fixture_v2.py (DELETED — bridging builder no longer needed)"
      - "tests/cross_runtime/generate_fixture.py (rewritten — self-contained v2 builder)"
      - "tests/cross_runtime/test_expr_parity.py (FIXTURE_PATH + count assertion + required-tags set updated to v2-only)"
      - "tests/conformance/test_arch_invariants.py (invariant 5 references v2 fixture and 250-case count)"
      - "js/flowforge-integration-tests/expr-parity.test.ts (repointed at v2 fixture)"
      - "js/flowforge-renderer/src/expr.ts (header comment updated)"
    test_path: "tests/cross_runtime/test_expr_parity.py"
    acceptance_criterion: |
      The legacy `expr_parity_200.json` is deleted; the canonical
      cross-runtime fixture is `expr_parity_v2.json` (250 cases). Both
      runtimes (Python `flowforge.expr` and TS
      `@flowforge/renderer`) agree byte-for-byte on every case.
      Architecture invariant 5 stays green; conformance suite
      reports 11/11 invariants pass.
    pre_deploy_checks:
      - "uv run pytest tests/cross_runtime/test_expr_parity.py -q — 253/253 passed"
      - "make audit-2026-cross-runtime — Python-side green (253 passed); JS-side gracefully skips on the pre-existing pnpm-ignored-builds blocker"
      - "make audit-2026-conformance — 11/11 invariants pass"
    rollback_plan: |
      git revert <sha>; restoring expr_parity_200.json + the bridging
      builder is mechanical (it's a pure delete with a re-pointing of
      test files). Reverting after the W3 commit is safe because no
      production runtime consumes the fixture — it's a CI-only
      determinism harness. The W1 ratchet
      `no_unparried_expr_in_step_template` keeps the template ↔
      fixture interlock intact regardless of which fixture name is
      canonical.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W3-closeout
  title: "W3 closeout — regen-diff verification, CHANGELOG, signoff rows, gate runs, plan status"
  wave: W3
  property: Quality
  worker: worker-w3-closeout
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "CHANGELOG.md (## [0.3.0-engr.3] — Wave 3 entries for items 9, 10, 11, 18, 21, new ratchet, fixture retirement)"
      - "docs/v0.3.0-engineering/signoff-checklist.md (W3 rows appended for items 9, 10, 11, 18, 21, ratchet, retirement, closeout)"
      - "docs/v0.3.0-engineering-plan.md (§7 status table — W3 marked completed)"
    acceptance_tests:
      - "scripts/ci/regen_flag_flip.sh — 6/6 byte-identical (3 examples × 2 form_renderer values)"
    pre_deploy_checks:
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS"
      - "make audit-2026-conformance — 11/11 invariants pass"
      - "make audit-2026-cross-runtime — Python-side 253/253 green; JS-side skip-with-reason on pnpm-install blocker"
      - "make audit-2026-visual-regression-dom — exits 0 with [SKIP] reason (pnpm-install blocker)"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
      - "uv run pytest python/flowforge-cli/tests/ -q — 443/443 green"
      - "scripts/ci/regen_flag_flip.sh — 6/6 byte-identical"
    determinism_proof: |
      Closeout artefacts are pure-functional documentation: CHANGELOG
      entries, signoff rows, and a status-table flip. The signoff
      rows mirror the pattern of W0/W1/W2 rows already in this file;
      no schema or runtime change.
    rollback_plan: |
      git revert <sha>; closeout is purely additive. Reverting
      restores the pre-W3 CHANGELOG / signoff / plan-status state
      without touching any of the implementation rows already
      landed in this checklist (W3 implementation rows for items 9,
      10, 11, 18, 21, ratchet, retirement live above and survive
      a closeout-only revert).
  follow_ups:
    - "pnpm-install unblock: once `pnpm approve-builds` runs for the workspace, the visual-regression baseline catalogs land in a follow-up PR alongside the JS-side cross-runtime parity green run."
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header). All 8 W3 verification gates collected at closeout time; one residual follow-up tracked above (pnpm-install unblock)."
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
```

---

## Wave W4a — Reliability backlog close-outs

```yaml
- item: W4a-item-3
  title: "Property-test bank per JTBD with ADR-003 pinned hypothesis seeds + property-coverage gate + retrofit"
  wave: W4a
  property: Reliable
  worker: worker-property
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/property_tests.py (NEW — per-JTBD generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/tests/test_property.py.j2 (NEW — hypothesis stateful machine template)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES entry for property_tests)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_JTBD_GENERATORS)"
      - "python/flowforge-cli/pyproject.toml (added hypothesis>=6.100,<7.0 runtime dep)"
      - "tests/property/generators/{_bundle_factory.py,test_<13 generators>_properties.py} (NEW — retrofit property tests for every W0-W3 generator)"
      - "tests/audit_2026/test_property_coverage_gate.py (NEW — every-generator-has-a-property-test gate)"
      - "tests/audit_2026/test_hypothesis_seed_uniqueness.py (NEW — ADR-003 seed format + 32-bit collision check)"
      - "Makefile (audit-2026-property-coverage target wired)"
      - "examples/insurance_claim/generated/backend/tests/claim_intake/test_claim_intake_properties.py (NEW)"
      - "examples/building-permit/generated/backend/tests/<5 jtbds>/test_<jtbd>_properties.py (NEW × 5)"
      - "examples/hiring-pipeline/generated/backend/tests/<5 jtbds>/test_<jtbd>_properties.py (NEW × 5)"
      - "CHANGELOG.md (## [0.3.0-engr.4a] entry for item 3 + property-coverage gate)"
    acceptance_tests:
      - "tests/audit_2026/test_property_coverage_gate.py::test_every_required_generator_has_a_property_test — green (13/13 generators covered)"
      - "tests/audit_2026/test_hypothesis_seed_uniqueness.py — 3/3 green (ADR-003 seed format, no intra-bundle collisions, retrofit seed pattern)"
      - "tests/property/generators/test_<13 generators>_properties.py — 13/13 green"
    pre_deploy_checks:
      - "make audit-2026-property-coverage — green"
      - "scripts/ci/regen_flag_flip.sh — 6/6 byte-identical (3 examples × 2 form_renderer flag values)"
      - "make audit-2026-conformance — 11/11 invariants pass"
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
      - "uv run pytest python/flowforge-cli/tests/ -q — 525/525 green"
    determinism_proof: |
      Per ADR-003 the per-JTBD hypothesis seed is computed at
      template-render time as ``int(sha256(jtbd_id)[:8], 16)`` — a
      32-bit pure function of the JTBD id, visible verbatim in the
      generated test source as ``_SEED = <int>``.  The emitted
      tests pin the stacked decorator pair
      ``@hypothesis.seed(_SEED)`` +
      ``@hypothesis.settings(derandomize=True, max_examples=200, ...)``
      (``hypothesis.seed`` is a separate decorator from
      ``hypothesis.settings`` in hypothesis 6.x; ADR-003 was amended
      in this wave to reflect the correct stacked-decorator syntax —
      the per-JTBD seed contract is unchanged) so two pytest
      invocations against the same generated suite produce
      identical example sequences.
      ``tests/audit_2026/test_hypothesis_seed_uniqueness.py``
      asserts (1) the seed value matches the ADR-003 sha256 formula,
      (2) no two JTBDs in the same example bundle share a seed
      (32-bit collision check), and (3) the retrofit
      hand-authored tests under ``tests/property/generators/``
      use a parallel deterministic seed pattern keyed on the
      generator name so they also stay byte-stable.
    cross_runtime_parity_proof: |
      Generator does not touch the expression evaluator. Hypothesis
      stateful machines operate on the synthesised Python-side state
      machine only; the TS evaluator is untouched. No fixture v2
      churn required; invariant 5 stays green against the existing
      ``expr_parity_v2.json`` corpus.
    rollback_plan: |
      git revert <sha>; the rollback removes the per-JTBD property
      test trees from each example's generated/ subdir, the new
      generator + template, the registry/pipeline entries, the
      retrofit tests under tests/property/generators/, the
      seed-uniqueness + coverage gate tests, the new Make target,
      and the hypothesis pyproject pin.  Property tests are purely
      additive; reverting after merge is mechanical.  Hypothesis
      stays installed on hosts that haven't re-resolved their
      lockfile — no breaking change.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD

- item: W4a-item-4
  title: "Guard-aware reachability checker — z3 opt-in extra (ADR-004) + per-JTBD + per-bundle summary"
  wave: W4a
  property: [Reliable, Functional]
  worker: worker-reachability
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/reachability.py (NEW — per-JTBD generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/reachability_summary.py (NEW — per-bundle aggregator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES entries for reachability + reachability_summary)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_JTBD_GENERATORS + _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/pyproject.toml ([project.optional-dependencies] reachability = [\"z3-solver==4.13.4.0\"])"
      - "pyproject.toml (z3-solver removed from [dependency-groups] dev; replaced by flowforge-cli[reachability])"
      - "python/flowforge-cli/src/flowforge_cli/commands/pre_upgrade_check.py (NEW --check-pyproject subcheck for z3 placement)"
      - "python/flowforge-cli/tests/test_pre_upgrade_check.py (extended with --check-pyproject row)"
      - "python/flowforge-cli/tests/test_reachability_generator.py (NEW — 15 unit tests covering both branches via z3-import mock)"
      - "Makefile (audit-2026-reachability target with z3-available branch + SKIP-with-install-hint branch)"
      - "examples/insurance_claim/generated/workflows/claim_intake/reachability.json + examples/insurance_claim/generated/workflows/reachability_summary.md (NEW)"
      - "examples/building-permit/generated/workflows/<5 jtbds>/reachability.json + examples/building-permit/generated/workflows/reachability_summary.md (NEW × 5 + 1)"
      - "examples/hiring-pipeline/generated/workflows/<5 jtbds>/reachability.json + examples/hiring-pipeline/generated/workflows/reachability_summary.md (NEW × 5 + 1)"
      - "CHANGELOG.md (## [0.3.0-engr.4a] entry for item 4)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_reachability_generator.py — 15/15 green (z3-available path, z3-missing placeholder, byte-stable summary aggregator, fixture-registry parity, examples emit artefacts, modules import cleanly)"
      - "python/flowforge-cli/tests/test_pre_upgrade_check.py — green (--check-pyproject row)"
    pre_deploy_checks:
      - "make audit-2026-reachability — green when z3 extra is installed; reports SKIP with install hint otherwise"
      - "scripts/ci/regen_flag_flip.sh — 6/6 byte-identical (3 examples × 2 form_renderer flag values)"
      - "make audit-2026-conformance — 11/11 invariants pass"
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
    determinism_proof: |
      Per ADR-004 the per-JTBD generator emits exactly one of two
      artefacts: ``reachability.json`` when ``import z3`` succeeds
      (full per-transition verdict) or
      ``reachability_skipped.txt`` with the documented placeholder
      text otherwise.  The placeholder body is a frozen string
      constant in the generator module; the JSON path sorts
      transitions by ``(state_id, event)`` and writes z3 verdicts
      in canonical JSON.  Per-bundle ``reachability_summary.md``
      iterates JTBDs in declaration order with a single
      ``status`` column (REACHABLE / UNREACHABLE / SKIPPED).  Two
      regens against the same bundle yield byte-identical output
      regardless of which branch fired; covered by
      ``test_byte_identical_regen_without_z3`` +
      ``test_summary_aggregator_marks_skipped_when_z3_missing``.
    cross_runtime_parity_proof: |
      Reachability evaluation is Python-side only (z3 runs on the
      host that invokes ``flowforge jtbd-generate``).  The TS
      evaluator does not consume the artefacts.  No fixture v2
      churn required; invariant 5 stays green.
    rollback_plan: |
      git revert <sha>; the rollback removes the per-JTBD +
      per-bundle reachability artefacts from each example, the
      two new generator modules, the pyproject extras
      reorganisation (reverting puts z3-solver back into
      [dependency-groups] dev — no host change because
      [dependency-groups] dev was already installed by every
      developer install), the pre-upgrade-check subcheck, and the
      Make target.  The reachability artefacts are purely
      advisory — no runtime code consumes them — so reverting is
      mechanical and safe.  Hosts that opted into
      ``flowforge-cli[reachability]`` keep z3 installed until
      ``uv sync`` re-resolves; nothing breaks in the meantime.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD

- item: W4a-property-coverage-gate
  title: "Property-coverage gate — every W0-W3 generator has a hypothesis property test + ADR-003 seed-uniqueness"
  wave: W4a
  property: Reliable
  worker: worker-property
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "tests/audit_2026/test_property_coverage_gate.py (NEW — REQUIRED_GENERATORS = 13 W0-W3 generators; one match per generator under tests/property/generators/test_<gen>_properties.py)"
      - "tests/audit_2026/test_hypothesis_seed_uniqueness.py (NEW — ADR-003 seed format check + 32-bit no-collision pin)"
      - "Makefile (audit-2026-property-coverage target — runs both gate tests)"
    test_path: "tests/audit_2026/test_property_coverage_gate.py, tests/audit_2026/test_hypothesis_seed_uniqueness.py"
    acceptance_criterion: |
      ``make audit-2026-property-coverage`` reports green when (1)
      every generator in REQUIRED_GENERATORS has at least one
      hand-authored property test under
      ``tests/property/generators/test_<gen>_properties.py`` and
      (2) every emitted per-JTBD property test pins
      ``_SEED = int(sha256(jtbd_id)[:8], 16)`` per ADR-003 with no
      32-bit collisions within an example bundle.  Adding a new
      W4-onward generator that lacks a retrofit fails the gate
      loud with the missing path listed.
    pre_deploy_checks:
      - "make audit-2026-property-coverage — green"
      - "make audit-2026-conformance — 11/11 invariants pass (no new invariant in W4a; property-coverage stays a gate, not an invariant)"
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS"
    rollback_plan: |
      git revert <sha>; the gate is purely additive — two test
      files under tests/audit_2026/ plus the Make target.
      Reverting removes the gate; the retrofit property tests
      under tests/property/generators/ stay in place and continue
      to run under the existing audit-2026-property matrix slot.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD

- item: W4a-item-5
  title: "SLA stress harness — k6 + Locust per JTBD (nightly cadence)"
  wave: W4a
  property: Reliable
  worker: worker-sla
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/sla_loadtest.py (NEW — per-JTBD generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES entry for sla_loadtest)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_JTBD_GENERATORS)"
      - "python/flowforge-cli/tests/test_sla_loadtest_generator.py (NEW — 37 unit tests)"
      - "scripts/audit_2026/run_sla_stress.sh (NEW — nightly wrapper, skips with reason when k6/locust absent)"
      - "Makefile (audit-2026-sla-stress target — nightly only)"
      - ".github/workflows/audit-2026.yml (schedule: cron + audit-2026-sla-stress job gated on schedule event)"
      - "examples/insurance_claim/generated/backend/tests/load/claim_intake/{k6_test.js,locust_test.py} (NEW)"
      - "examples/building-permit/generated/backend/tests/load/<5 jtbds>/{k6_test.js,locust_test.py} (NEW)"
      - "examples/hiring-pipeline/generated/backend/tests/load/<5 jtbds>/{k6_test.js,locust_test.py} (NEW)"
      - "CHANGELOG.md (## [0.3.0-engr.4a] entry for item 5)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_sla_loadtest_generator.py — 37/37 green"
    pre_deploy_checks:
      - "bash scripts/check_all.sh step 8 (regen-diff) — 3/3 examples byte-identical"
      - "scripts/ci/regen_flag_flip.sh — 6/6 byte-identical (3 examples × 2 form_renderer flag values)"
      - "make audit-2026-conformance — 11/11 invariants pass"
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
    determinism_proof: |
      Pure-functional string assembly. ``_derive_load_params`` is a
      total deterministic function of ``sla.breach_seconds``; the k6
      / Locust scripts are line-by-line list joins with no random
      ids, no timestamps, no dict iteration. JTBDs without
      ``sla.breach_seconds`` skip silently (empty list return), so
      pre-W4a fixtures regen byte-identically. Both
      ``form_renderer`` flag values produce identical SLA harness
      output (the harness is invariant to that flag); the
      ``test_form_renderer_flag_does_not_affect_sla_harness`` test
      pins this so the regen-flag-flip gate keeps producing 6/6
      byte-identical matches.
    cadence_proof: |
      Per-PR runs are excluded by the ``if: github.event_name == 'schedule'``
      gate in .github/workflows/audit-2026.yml. The wrapper script
      additionally skips with a clear reason if k6/locust aren't on
      PATH, so any ad-hoc invocation in a non-nightly context exits
      0 cleanly. Matches docs/v0.3.0-engineering-plan.md §10:
      "SLA stress harness (item 5) runs nightly; not per-PR."
    rollback_plan: |
      git revert <sha>; the rollback removes the per-JTBD harness
      tree from each example's generated/ subdir + the new wrapper
      + Make target + workflow job + the registry/pipeline
      entries. The SLA harness is purely additive (skip-silently
      for SLA-less JTBDs), so reverting after merge is mechanical
      and safe.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W4a-item-14
  title: "Faker-driven seed data — per-bundle generator + make seed target"
  wave: W4a
  property: Functional
  worker: worker-seed
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/seed_data.py (NEW — per-bundle generator)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/templates/seed_data.py.j2 (NEW)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/generators/_fixture_registry.py (CONSUMES entry for seed_data)"
      - "python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py (registered in _PER_BUNDLE_GENERATORS)"
      - "python/flowforge-cli/pyproject.toml (added faker>=25,<37 runtime dep)"
      - "python/flowforge-cli/tests/test_jtbd_seed_data.py (NEW — 22 unit tests)"
      - "Makefile (new top-level make seed target with SEED_EXAMPLE / SEED_PACKAGE knobs)"
      - "examples/insurance_claim/generated/backend/seeds/insurance_claim_demo/{__init__.py,__main__.py,seed_claim_intake.py} (NEW)"
      - "examples/building-permit/generated/backend/seeds/building_permit/{__init__.py,__main__.py,seed_<5 jtbds>.py} (NEW)"
      - "examples/hiring-pipeline/generated/backend/seeds/hiring_pipeline/{__init__.py,__main__.py,seed_<5 jtbds>.py} (NEW)"
      - "CHANGELOG.md (## [0.3.0-engr.4a] entry for item 14)"
    acceptance_tests:
      - "python/flowforge-cli/tests/test_jtbd_seed_data.py — 22/22 green"
    pre_deploy_checks:
      - "bash scripts/check_all.sh step 8 (regen-diff) — 3/3 examples byte-identical"
      - "make audit-2026-conformance — 11/11 invariants pass"
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
      - "uv run pytest python/flowforge-cli/tests/ — 525/525 green (no pre-existing test broken)"
    determinism_proof: |
      Faker is seeded deterministically from
      ``int(sha256("<package>:<jtbd_id>")[:8], 16)`` at module load
      time, so two ``seed()`` calls against the same database produce
      byte-identical seed rows.  The generator itself is pure-functional
      string assembly: ``_faker_expr`` is a total deterministic function
      of the field's kind / label / validation; ``_seed_event_paths``
      BFS-walks the synthesised transitions in declaration order with
      ``(priority, event, to_state)`` tie-breaking.  The dispatch order
      matches the JTBD's state declaration so the emitted SEED_PATHS
      tuple is byte-stable.  The module reads no flag-conditioned
      bundle field (verified by ``test_seed_data`` — same output under
      ``form_renderer = "skeleton"`` and ``"real"``), so per-bundle
      regen-diff is byte-identical for every flag combination.  Enum
      options are sorted before emission so dict-iteration order
      cannot perturb the source-text dispatch.
    cadence_proof: |
      ``make seed`` is the operator-facing entrypoint.  Defaults to
      ``examples/insurance_claim`` / package
      ``insurance_claim_demo`` and walks the per-JTBD modules via
      ``python -m seeds.<package>``.  Not run on per-PR CI — seeding
      a host database is an operator action, not a regen-diff
      gate.  Per-PR coverage stays in
      ``test_jtbd_seed_data.py`` which exercises every dispatch
      branch + the BFS path-finder + the byte-deterministic regen
      contract through the in-process pipeline.
    rollback_plan: |
      git revert <sha>; the rollback removes the per-bundle seeds tree
      from each example's generated/ subdir, the new generator + template,
      the registry/pipeline entries, the make target, the faker pyproject
      pin, and the test file.  The seed_data generator is purely
      additive (no public API change to flowforge-core, no migration
      surface, no schema change), so reverting after merge is
      mechanical and safe.  The ``faker`` runtime dep stays installed
      until ``uv sync`` re-resolves the lockfile; downstream hosts
      that haven't re-installed are unaffected.
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header)"
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-10
    commit_sha: TBD

- item: W4a-closeout
  title: "W4a closeout — regen-diff verification, CHANGELOG, signoff rows, gate runs, plan status flip, ADR-003 syntax correction"
  wave: W4a
  property: Quality
  worker: worker-w4a-closeout
  status: implementation_landed_pending_signoff
  evidence:
    files_changed:
      - "CHANGELOG.md (## [0.3.0-engr.4a] — Wave 4a entries for items 3, 4, 5, 14, the new property-coverage gate, and the example bundle baselines note)"
      - "docs/v0.3.0-engineering/signoff-checklist.md (W4a rows appended for items 3, 4, property-coverage-gate, 5, 14, and this closeout)"
      - "docs/v0.3.0-engineering-plan.md (§7 status table — W4a flipped from pending to ✅ completed)"
      - "docs/v0.3.0-engineering/adr/ADR-003-hypothesis-seed-pinning.md (example syntax corrected from `settings(seed=N)` to the stacked `@seed(N) @settings(...)` form — the per-JTBD seed contract `int(sha256(jtbd_id)[:8], 16)` stays unchanged; bug flagged by worker-reachability on worker-property's implementation)"
    acceptance_tests:
      - "scripts/ci/regen_flag_flip.sh — 6/6 byte-identical (3 examples × 2 form_renderer flag values)"
    pre_deploy_checks:
      - "bash scripts/ci/ratchets/check.sh — 7/7 PASS (no new ratchet in W4a)"
      - "make audit-2026-conformance — 11/11 invariants pass"
      - "make audit-2026-property-coverage — green (13 generators covered, 3 seed-uniqueness checks green)"
      - "make audit-2026-reachability — green when z3 extra installed; reports SKIP with install hint otherwise"
      - "make audit-2026-cross-runtime — Python-side green; JS-side skip-with-reason on pre-existing pnpm-install blocker (carried over from W3)"
      - "make audit-2026-sla-stress — workflow YAML schedules it nightly only via `schedule: - cron: \"0 3 * * *\"` and the job gate `if: github.event_name == 'schedule'` per docs/v0.3.0-engineering-plan.md §10; per-PR runs never trigger it"
      - "uv run pyright python/flowforge-cli/src --pythonversion 3.11 — 0 errors, 0 warnings"
      - "uv run pytest python/flowforge-cli/tests/ -q — 525/525 green"
      - "scripts/ci/regen_flag_flip.sh — 6/6 byte-identical"
    determinism_proof: |
      Closeout artefacts are pure-functional documentation: CHANGELOG
      entries, signoff rows, and a status-table flip.  The signoff
      rows mirror the pattern of W0/W1/W2/W3 rows already in this
      file; no schema or runtime change.  Regen-diff determinism
      is established by the four implementation rows above; this
      row consumes their evidence and pins it to the closeout
      commit SHA.
    rollback_plan: |
      git revert <sha>; closeout is purely additive.  Reverting
      restores the pre-W4a CHANGELOG / signoff / plan-status state
      without touching any of the implementation rows already
      landed in this checklist (W4a implementation rows for items
      3, 4, 5, 14 + the property-coverage gate live above and
      survive a closeout-only revert).
  follow_ups:
    - "pnpm-install unblock (carried over from W3): once `pnpm approve-builds` runs for the workspace, the JS-side cross-runtime parity green run completes; nothing in W4a depends on this."
  architecture_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
    note: "single-stakeholder approval pattern (see roles header). All W4a verification gates collected at closeout time; one residual follow-up tracked above (pnpm-install unblock, from W3)."
  qa_lead_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
  release_manager_signoff:
    signer: Nyimbi Odero
    date: 2026-05-11
    commit_sha: TBD
```

---

*This file is the v0.3.0-engineering equivalent of
`docs/audit-2026/signoff-checklist.md`. Treated as a living doc — wave
sections are appended as W1..W4b land.*
