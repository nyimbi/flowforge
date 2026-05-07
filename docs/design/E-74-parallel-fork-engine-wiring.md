# E-74: parallel_fork engine wiring

**Status**: design + scaffold landed; runtime wiring pending
**Origin**: surfaced during E-45 e2e suite work (worker-eng-4) — the
`parallel_fork` / `parallel_join` DSL primitives are declared in
`StateKind` and the JSON schema, but `engine.fire()` never dispatches
through them. The audit-2026 IT-02 acceptance was satisfied via
snapshot+clone+replay because that's the property the audit cared about
(replay determinism), not the literal fork primitive. This ticket
delivers the literal primitive.
**Not an audit finding.** Tracked as a post-1.0 architectural follow-up.

---

## 1. Current state

- DSL: `StateKind` enum has `"parallel_fork"` + `"parallel_join"` literals
  (workflow_def.py:51-56).
- Schema: `framework/python/flowforge-core/src/flowforge/dsl/schema/workflow_def.schema.json`
  validates these kinds.
- Runtime primitives: `engine/tokens.py` has `Token` + `TokenSet`
  dataclasses; `_fork.py` (NEW) carries the planned helper signatures.
- `engine/fire.py`: zero references to `parallel_fork` / tokens. Firing
  into a fork state today is a no-op transition.

## 2. Target behaviour

A workflow definition like:

```yaml
states:
  - name: triage
    kind: manual_review
  - name: fork_review
    kind: parallel_fork
  - name: branch_a
    kind: automatic
  - name: branch_b
    kind: automatic
  - name: join_review
    kind: parallel_join
  - name: closed
    kind: terminal_success

transitions:
  - {from: triage,       to: fork_review,  on: ready}
  - {from: fork_review,  to: branch_a}
  - {from: fork_review,  to: branch_b}
  - {from: branch_a,     to: join_review,  on: a_done}
  - {from: branch_b,     to: join_review,  on: b_done}
  - {from: join_review,  to: closed,       on: all_branches_joined}
```

Should advance as:

1. `fire(triage, "ready")` → state becomes `fork_review`.
2. **Fork dispatch**: when `fire()` reaches a `parallel_fork` state, it
   creates one `Token` per outgoing transition (here: branch_a, branch_b)
   and adds them to `instance.tokens`. The instance's "primary" state
   stays as the fork state until joined.
3. `fire(branch_a, "a_done", token_id=...)` advances token a to
   `join_review` and `tokens.remove(a)`.
4. `fire(branch_b, "b_done", token_id=...)` advances token b to
   `join_review`. Now `tokens.count_in_region(fork_review) == 0`.
5. **Join collapse**: `engine` synthetically fires
   `(join_review, "all_branches_joined")` once the last token in the
   region exits. State becomes `closed`.

## 3. Implementation phases

### Phase 1: Instance.tokens field

`flowforge.engine.snapshots.Instance` gains:

```python
@dataclass
class Instance:
    ...
    tokens: TokenSet = field(default_factory=TokenSet)
```

Snapshot store + audit canonical body must include tokens for replay
determinism (E-37 invariant 7) — adds to canonical_json schema.

### Phase 2: Fork dispatch in fire()

In `engine/fire.py` after the existing two-phase commit lands a
transition:

```python
if state_def.kind == "parallel_fork":
    for branch in outgoing_transitions(state_def):
        token = Token(
            id=uuid7str(),
            region=state_def.name,
            state=branch.to,
        )
        instance.tokens.add(token)
```

### Phase 3: Per-token transition dispatch

`fire(instance_id, event, *, token_id=None)`:

- If `token_id` is provided, advance only that token.
- If `token_id` is `None`, advance the primary state.
- Fork-region states cannot be advanced by primary fire if any token
  is still alive in that region — raise `RegionStillForkedError`.

### Phase 4: Join barrier

After every per-token advance, check:

```python
if state_def.kind == "parallel_join":
    instance.tokens.remove(token.id)
    if instance.tokens.count_in_region(state_def.region) == 0:
        # All branches done → synthetic primary fire
        instance.state = state_def.name
        if (next := outgoing_transitions(state_def)):
            instance.state = next[0].to
```

### Phase 5: Tests + invariant 9

Add `tests/conformance/test_arch_invariants.py::test_invariant_9_fork_join_safe`:
1. fork-of-2 + symmetric join → final state == join target
2. fork-of-2 + unbalanced fire (a, a, b) → only one a-advance, second a is
   `TokenAlreadyConsumedError`
3. fork-of-N + replay of same event sequence → byte-identical state +
   token order (extends invariant 3 to fork primitive)

E2E flow 4 in E-45 is upgraded to use literal `parallel_fork` instead of
snapshot+clone.

## 4. Risks

- **R-1 (engine regression)**: fire.py has 5+ landed audit fixes
  (E-32 EPIC, E-39, E-40). Any wiring change risks regressing
  conformance invariants 2 + 4. Mitigation: gate behind a `forks_enabled`
  feature flag for one minor; strict-required-green on invariants 2 + 4
  for every PR touching fire.py.
- **R-2 (canonical body break)**: adding `tokens` to canonical_json
  changes E-37 audit-chain bytes for any workflow that uses fork. Two
  options: (a) tokens are out-of-band, not in canonical body (audit
  records primary state only — readers reconstruct tokens from
  per-token transition events); (b) bump canonical body version, force
  re-bake of golden fixture. Prefer (a).
- **R-3 (replay-determinism)**: token IDs are uuid7 (per E-39); replay
  must use deterministic seeds. Either record token IDs in the audit
  event (option b above) or seed the uuid generator from
  `(instance_id, region, branch_index)`.

## 5. Scope guard

This ticket does NOT include:
- Compensation across forked branches (covered by E-40 saga ledger;
  per-token compensation is invariant 4 follow-up).
- Cross-region token interaction (forks-of-forks).
- Time-bounded join (timeout while waiting for tokens).

Those are explicit follow-ons (E-75, E-76, E-77) once Phase 1-5 lands.

## 6. Acceptance

- Conformance invariant 9 green.
- E-45 flow 3 uses literal parallel_fork.
- `forks_enabled` feature flag default-on after one minor of opt-in.
- No regression of invariants 2, 3, 4, 7 on the existing test suite.

## 7. References

- `framework/docs/audit-fix-plan.md` §10.3 close-out criterion 4
  (architectural deferrals must have explicit successor tickets).
- worker-eng-4 E-45 stop-and-report message (audit-2026 session).
- `framework/docs/audit-2026/backlog.md`.
