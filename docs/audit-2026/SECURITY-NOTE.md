# SECURITY-NOTE — audit-2026

This file records the security-impacting changes shipped under audit-2026 so
operators can act on each one before upgrading.  Each entry maps back to a
ticket (`E-XX`) and the originating findings.

> Per-fix mitigations track the F-2 ("ship incomplete") and F-7 ("year-old
> prod image breaks on env-var change") risks recorded in
> `framework/docs/audit-fix-plan.md` §2.

---

## E-37b — Hub trust gate (P0; JH-01)

**Shipped**: framework/python/flowforge-jtbd-hub (S0).

### What changed

* **JH-01 (BREAKING).**  Default-deny for unsigned package installs.
  - `Package.signed_at_publish: bool` is persisted at publish time.
    `True` only when the package arrived with a signature that verified
    against the hub signing port; `False` when the publisher used
    `allow_unsigned=True`.
  - `PackageRegistry.install(...)` raises `UnsignedPackageRejected` for
    any package whose `signed_at_publish=False` unless the caller
    explicitly passes `accept_unsigned=True`.  The opt-in path emits a
    `PACKAGE_INSTALL_UNSIGNED` audit event through the new optional
    `PackageRegistry(audit_hook=...)` constructor hook (or per-call
    `audit_emit=...`).
  - The orthogonal `verified_publishers_only` gate still applies to
    accepted-unsigned installs; it does not piggy-back on
    `accept_unsigned`.

* **JH-01 sanitised errors.**  Both `UnsignedPackageRejected` and
  `UntrustedSignatureError` messages no longer contain the rejected
  internal `key_id` value.  Pre-fix, the cleartext error gave an
  attacker partial enumeration of the hub's trust set.

### Operator action required

1. Hosts that previously installed unsigned packages by accident (e.g.
   forgetting to flip `allow_untrusted=true`) will now see explicit
   `UnsignedPackageRejected`.  Either:
   - **Recommended**: re-publish the package with a real signature.
   - **Bridge**: pass `accept_unsigned=True` on the install call (router
     layer surfaces this as `?accept_unsigned=true`); each accepted
     install emits a `PACKAGE_INSTALL_UNSIGNED` audit event.

2. Wire the constructor `audit_hook` if you want centralised observability
   of unsigned-install events without changing every call site:

   ```python
   def audit_sink(event_type: str, payload: dict) -> None:
       audit_log.record(event_type, payload)

   registry = PackageRegistry(signing=..., audit_hook=audit_sink)
   ```

### Observability

* Audit event: `PACKAGE_INSTALL_UNSIGNED` (payload includes `name`,
  `version`, `reason`).  Alert on rate above your published-baseline.

### Rollback

Revert framework version; no DB migration.  The `signed_at_publish`
field is internal to `Package` (not on the wire manifest), so revert is
forward-compatible.

---

## E-34 — Crypto rotation (P0; SK-01, SK-02, SK-03)

**Shipped**: framework/python/flowforge-signing-kms (S0).

### What changed

* **SK-01 (BREAKING, opt-in deprecation window).**  `HmacDevSigning()` no
  longer falls back to a hard-coded secret.  Instantiating without
  `FLOWFORGE_SIGNING_SECRET` (or an explicit `secret=` / `keys=`
  argument) raises `RuntimeError("explicit secret required …")`.

  The legacy fallback is reachable for one minor-version deprecation
  window via `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`, which logs a loud
  `WARNING` (`!!! INSECURE DEFAULT IN USE !!!`) and increments the
  Prometheus counter `flowforge_signing_secret_default_used_total`.

* **SK-02.**  `HmacDevSigning(keys={kid: secret}, current_key_id=kid)`
  carries a per-`key_id` secret map.  `verify()` raises
  `flowforge_signing_kms.UnknownKeyId` when called with a `key_id` the
  signer does not know — distinct from "wrong signature" so callers can
  audit the configuration error separately from a tampered payload.

* **SK-03.**  KMS adapters (`AwsKmsSigning`, `GcpKmsSigning`) now
  classify provider exceptions:
  - transient (throttling / network / internal / deadline) →
    `KmsTransientError` so the caller can retry with backoff.
  - unknown key id (AWS `NotFoundException`, GCP `NotFound`) →
    `UnknownKeyId`.
  - permanent invalid signature → `verify()` returns `False`
    (branch-friendly default — no exception).

### Operator action required

1. **Before upgrading** the framework version that contains E-34, run
   the new pre-upgrade check:

   ```bash
   uv run flowforge_pre_upgrade_check signing
   ```

   It prints `OK` if the host has either:
   - `FLOWFORGE_SIGNING_SECRET` set, **or**
   - `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` set (with a loud warning that
     this opt-in is removed at the next minor release).

   It exits non-zero with a clear remediation message otherwise — wire
   it into your CI/CD gate before bumping the version.

2. **Migration guidance.**  If you currently rely on the old default
   secret (you almost certainly should not in production):
   - **Recommended**: set `FLOWFORGE_SIGNING_SECRET` to a real secret in
     your secrets manager and rotate any signatures produced under the
     old hard-coded default.  Treat them as untrusted.
   - **Bridge**: set `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` for one minor
     version, accept the loud-log warnings, monitor
     `flowforge_signing_secret_default_used_total > 0` in Prometheus,
     then drop the flag once the metric reads zero.

3. **Key rotation.**  When rotating signing keys, switch to the map
   form so old signatures keep verifying:

   ```python
   HmacDevSigning(
       keys={"key-v1": old_secret, "key-v2": new_secret},
       current_key_id="key-v2",
   )
   ```

### Observability

* Counter: `flowforge_signing_secret_default_used_total` (incremented
  whenever a process starts under the legacy opt-in flag — alert on
  `> 0` in production).
* CI ratchet: `scripts/ci/ratchets/no_default_secret.sh` greps the
  source tree for any reintroduction of the legacy hard-coded default.

### Rollback

Revert the framework version and re-deploy the previous image; no DB
migration is involved.

---

*Append new entries above this line, newest first, as additional E-XX
fixes ship.*
