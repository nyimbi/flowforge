# flowforge-jtbd-hub changelog

## 0.1.0 — Unreleased

- **[SECURITY] (audit-2026 E-37b, P0)** Explicit hub trust gate (JH-01).
  - `Package.signed_at_publish: bool` is now persisted at publish time:
    `True` when the package arrived with a signature that verified against
    the hub signing port; `False` when the publisher used `allow_unsigned=True`
    (dev-only convenience).
  - `PackageRegistry.install(...)` raises `UnsignedPackageRejected` by
    default for any package whose `signed_at_publish=False`.  Callers must
    opt in explicitly with `accept_unsigned=True`; that path also emits a
    `PACKAGE_INSTALL_UNSIGNED` audit event through the optional
    `PackageRegistry(audit_hook=...)` constructor hook (or per-call
    `audit_emit=...`) so operators can attribute the decision.
  - When `accept_unsigned=True` is granted on an unsigned package, the
    signature-trust gate is structurally inert (no signature exists for the
    trust set to evaluate) but the orthogonal `verified_publishers_only`
    gate continues to apply.
  - `UnsignedPackageRejected` and `UntrustedSignatureError` messages no
    longer leak the rejected `key_id` — pre-fix, the cleartext message
    gave an attacker partial enumeration of the hub's trust set.
- E-24: jtbd-hub registry service.
  - `PackageManifest` pydantic model + canonical-JSON signing payload
    (RFC-8785-aligned; signature field excluded from the hash domain).
  - `PackageRegistry` with `publish`, `resolve`, `install_payload`
    (download counter), `search`, `rate`, `demote`, `mark_verified`.
  - `ReputationScorer` Protocol + `DefaultReputationScorer`
    (downloads × average-stars × age-decay over 180-day window).
  - `TrustConfig` with `resolve_trust_config(...)` per arch §11.16
    lookup chain (flag > env > user > system > pyproject > default).
  - FastAPI app via `create_app(registry, signing, *, admin_token=...)`
    with the documented endpoints. Admin endpoints (demote, verify
    badge) gated by `admin_token`. Install endpoint refuses
    untrusted signatures unless the caller passes
    `?allow_untrusted=true`.
  - HMAC dev signing exercised end-to-end via
    `flowforge_signing_kms.HmacDevSigning`.
