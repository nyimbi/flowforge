# scripts/ci/ratchets

Grep-based regression gates for audit-fix-plan §F-6 / R-6.

Each script under this directory enforces one anti-pattern across the
runtime code paths. `check.sh` runs every script and reports a summary.
`baseline.txt` records the legitimate exceptions; new matches outside
the baseline fail CI.

## Layout

| File | Audit refs | Purpose |
|---|---|---|
| `check.sh` | — | runs every ratchet, aggregates result |
| `baseline.txt` | — | per-ratchet exception list (security-review gated) |
| `no_default_secret.sh` | SK-01 → E-34 | bans `FLOWFORGE_SIGNING_SECRET` defaults + dev-secret literals |
| `no_string_interp_sql.sh` | T-01, J-01, OB-01 | bans f-string / `.format()` / `%` SQL |
| `no_eq_compare_hmac.sh` | NM-01 → E-54 | bans `==` on HMAC digests; mandates `hmac.compare_digest` |
| `no_except_pass.sh` | J-10, JH-06, CL-04 | bans `except Exception: pass` swallow |

## Adding a new ratchet

1. Add a shell script alongside the existing ones; exit 0 on green, 1 on violation.
2. Append the script name to `RATCHETS=(...)` in `check.sh`.
3. Add a `## ratchet=<name>` header to `baseline.txt`.
4. Document the rule in this README's table and reference the audit
   finding it enforces.

## Updating the baseline

Updating `baseline.txt` requires security-team review. The accepted format
for a baselined occurrence is the exact `path:line:matched_text` line that
the ratchet prints when it fails. Land the code change and the baseline
update in the same PR.
