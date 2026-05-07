# NL → JTBD prompt-injection: residual-risk note

**Status**: living doc. Audit-2026 J-05.
**Owner**: flowforge-jtbd / ai team.

## Scope

`flowforge_jtbd.ai.nl_to_jtbd._sanitise_description` is the gate
between free-text user input and the LLM prompt that drafts a `JtbdSpec`.
It implements two layers of defence against prompt-injection in the
**direct** input path:

1. **Token strip** — known instruction-protocol markers
   (`<|im_start|>`, `<|im_end|>`, `<|system|>`, `<|user|>`,
   `<|assistant|>`, `[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>`) are
   removed before the description ever reaches the prompt.
2. **Phrase reject** — descriptions that match instruction-override
   patterns (`ignore previous instructions`, `disregard prior rules`,
   `system: you are`, `jailbreak`, `role: system`) raise
   `PromptInjectionRejected` so the human author sees what was rejected.

A 50-prompt adversarial test bank
(`tests/unit/test_E_47_acceptance.py::test_J_05_*`) exercises both
layers and pins ≥45/50 catches as the ratchet.

## Indirect injection

The system prompt wraps the user description in
`<user_description>...</user_description>` tags and explicitly tells
the model to treat content inside the tags as untrusted text — never
as instructions. We rely on the LLM to honour this; even a strong
model is not a hard guarantee, so this layer is **defence in depth**,
not a primary control.

## Known residual risks

The following classes of attack are **not fully blocked** by the
current pipeline. Any production deployment must layer additional
controls (output validation, rate limiting, human review) where the
risk profile demands it.

### 1. Paraphrased instruction-override

The phrase reject is a finite list. An attacker can paraphrase
("kindly forget the above rules") and slip past. Mitigation: the
output is structurally validated (`JtbdSpec.model_validate`) and a
maximum of ONE retry is allowed — repeated failures surface to the
human author.

### 2. Embedded base64 / encoded payload

Token-strip is plaintext. A user description containing
`<|im_start|>` base64-encoded would slip through. Mitigation: the
output validator rejects spec fields that look encoded; downstream
consumers SHOULD apply a content filter on `description` before
storing.

### 3. Indirect injection via reference data

If a deployment populates JTBD descriptions from external sources
(scraped pages, ticketing systems), those sources are also untrusted.
The current sanitiser only knows about the LLM-prompt layer. Mitigation:
treat reference data as untrusted at ingestion, not at NL→JTBD time.

### 4. Multi-turn jailbreak

Single-turn analysis cannot detect a multi-turn refinement attack
where benign turns build context for a final exploit. Mitigation:
NL→JTBD is single-turn by construction — but if an integration
chains multiple calls, evaluate each call's output independently.

### 5. Output-side leakage

A malicious LLM response could embed instruction sequences in JSON
field values that downstream tools render. Mitigation: callers MUST
treat LLM output as untrusted (escape on render, validate against the
JSON schema, never `eval`).

## Test bank — adversarial coverage

`tests/unit/test_E_47_acceptance.py::_ADVERSARIAL_BANK` ships 50
prompts spanning:

- direct overrides (10 variations of "ignore previous instructions")
- role impersonation (`system:`, `<|system|>`, `<<SYS>>`, `[INST]`)
- jailbreak phrasing
- tag-injection / structured spoofing
- token-only payloads
- mixed-context attempts (FNOL + override)

Acceptance threshold: **≥45/50 caught**. Below that, the test fails
the build. Five "near misses" are tolerated because the phrase list
will always be a moving target — any structurally-impossible 50/50
gate would create a false sense of security.

## What to do when extending the pipeline

* Add new patterns to `_INJECTION_PATTERNS` (regex) or
  `_INJECTION_TOKENS` (literal strings) — both feed the test gate.
* Add 5+ new adversarial prompts to `_ADVERSARIAL_BANK` for any new
  attack class you observe in the wild.
* Update this doc with the new residual-risk class.
* Open a security-review ticket; do NOT silently broaden the gate.
