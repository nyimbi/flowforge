# flowforge-jtbd-hub changelog

## 0.1.0 — Unreleased

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
