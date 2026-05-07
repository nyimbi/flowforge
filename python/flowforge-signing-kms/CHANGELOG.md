# flowforge-signing-kms changelog

## Unreleased

- **[SECURITY-BREAKING] (audit-2026 E-34, P0)** Crypto rotation hardening (SK-01, SK-02, SK-03).
  - **SK-01.**  `HmacDevSigning()` no longer falls back to a hard-coded
    legacy secret.  Calling without `FLOWFORGE_SIGNING_SECRET` (or an explicit
    `secret=` / `keys=` argument) raises `RuntimeError("explicit secret
    required …")`.  Operators may opt in to the legacy default for one
    minor-version deprecation window via `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`;
    that path logs `WARNING !!! INSECURE DEFAULT IN USE !!!` and increments
    the `flowforge_signing_secret_default_used_total` counter.  See
    `framework/docs/audit-2026/SECURITY-NOTE.md` E-34 for migration guidance
    and `flowforge pre-upgrade-check signing` for the pre-upgrade gate.
  - **SK-02.**  New `HmacDevSigning(keys={kid: secret}, current_key_id=kid)`
    constructor form lets a single signer carry multiple key-id → secret
    entries so old signatures keep verifying after rotation.  `verify()`
    raises `flowforge_signing_kms.UnknownKeyId` if the `key_id` is not in
    the configured map.  Legacy `HmacDevSigning(secret=…, key_id=…)` form
    remains backward-compatible.
  - **SK-03.**  KMS adapters classify provider exceptions:
    `ThrottlingException` / `RequestLimitExceeded` / `KMSInternalException`
    / `DependencyTimeoutException` / GCP `DeadlineExceeded` /
    `ServiceUnavailable` / `ResourceExhausted` → `KmsTransientError`
    (caller retries with backoff).  AWS `NotFoundException` / GCP
    `NotFound` → `UnknownKeyId`.  Permanent invalid signatures →
    `verify()` returns `False` (no exception).  New `KmsSignatureInvalid`
    type declared for callers that want to differentiate explicitly.
  - New error types re-exported from package root:
    `SigningKmsError`, `UnknownKeyId`, `KmsTransientError`,
    `KmsSignatureInvalid`.

## 0.1.0 (2026-05-05)

- `HmacDevSigning`: HMAC-SHA256 local-dev backend with env-var secret and key rotation support.
- `AwsKmsSigning`: AWS KMS adapter (HMAC_SHA_256 or asymmetric RSA), tested via moto.
- `GcpKmsSigning`: GCP Cloud KMS adapter (MAC or asymmetric RSA), tested via stub client.
- All three satisfy the `SigningPort` protocol from `flowforge.ports.signing`.
