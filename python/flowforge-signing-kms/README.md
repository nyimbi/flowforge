# flowforge-signing-kms

Signing adapters for the flowforge `SigningPort` protocol: HMAC-SHA256 for local development, AWS KMS and GCP Cloud KMS for production.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
# base (HmacDevSigning only)
uv pip install flowforge-signing-kms

# with AWS KMS support
uv pip install "flowforge-signing-kms[aws]"

# with GCP KMS support
uv pip install "flowforge-signing-kms[gcp]"
```

## What it does

This package provides three concrete implementations of the flowforge `SigningPort` protocol. `HmacDevSigning` uses HMAC-SHA256 with a key map stored in process memory — it is for local development and CI only and must not be used in production. `AwsKmsSigning` delegates to AWS KMS using `boto3`; `GcpKmsSigning` delegates to GCP Cloud KMS using `google-cloud-kms`. Both KMS adapters work against live service or against mocks (moto for AWS, injected stub for GCP) so integration tests need no real cloud credentials.

The E-34 audit round removed the hard-coded fallback secret that earlier versions used when `FLOWFORGE_SIGNING_SECRET` was absent. `HmacDevSigning` now raises `RuntimeError` at construction time if no secret material is available. A one-minor deprecation bridge exists: set `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` to restore the legacy default with loud-log warnings and a Prometheus counter. Both KMS adapters run their blocking `boto3`/gRPC calls via `asyncio.to_thread` (SK-04) so they do not stall the event loop during the 50–500 ms KMS round-trip.

The package does not provide key generation, key storage, or rotation scheduling. It does not wrap `cryptography` or any other local asymmetric library — production asymmetric signing goes through KMS directly.

## Quick start

```python
import asyncio
import os
from flowforge_signing_kms import HmacDevSigning, AwsKmsSigning, GcpKmsSigning

# Local dev — single key form
os.environ["FLOWFORGE_SIGNING_SECRET"] = "dev-secret-min-32-chars-long-ok"
signer = HmacDevSigning(key_id="key-v1")
sig = asyncio.run(signer.sign_payload(b"payload"))
ok = asyncio.run(signer.verify(b"payload", sig, "key-v1"))
assert ok

# Key rotation — carry old key for verifying existing signatures
signer = HmacDevSigning(
	keys={"key-v1": "old-secret", "key-v2": "new-secret"},
	current_key_id="key-v2",
)
print(signer.known_key_ids())  # ['key-v1', 'key-v2']

# AWS KMS (moto-compatible in tests)
aws_signer = AwsKmsSigning(key_id="alias/my-signing-key", region_name="us-east-1")

# GCP KMS — inject a stub client in tests
gcp_signer = GcpKmsSigning(
	key_version_name="projects/p/locations/global/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1",
	use_mac=True,
)
```

## Public API

- `HmacDevSigning` — HMAC-SHA256 local-dev backend; key map + rotation support.
- `AwsKmsSigning` — AWS KMS backend (`HMAC_SHA_256` default; `RSASSA_PKCS1_V1_5_SHA_256` via `algorithm=`).
- `GcpKmsSigning` — GCP Cloud KMS backend (MAC or asymmetric RSA via `use_mac=`).
- `SigningKmsError` — base exception class.
- `UnknownKeyId` — raised when `verify()` is called with a `key_id` the signer has no record of.
- `KmsTransientError` — raised on recoverable KMS failures (throttling, network error, internal error); caller should retry with backoff.
- `KmsSignatureInvalid` — declared for callers that need to log permanent-invalid events explicitly; `verify()` returns `False` by default.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `FLOWFORGE_SIGNING_SECRET` | — | **Required** for `HmacDevSigning`. Set to a real secret in all environments. |
| `FLOWFORGE_SIGNING_KEY_ID` | `dev-key-1` | Optional key id when using the single-key form. |
| `FLOWFORGE_ALLOW_INSECURE_DEFAULT` | — | Set to `1` to activate the deprecation bridge (one minor version only). Emits warnings and increments `flowforge_signing_secret_default_used_total`. |

## Audit-2026 hardening

- **SK-01** (E-34): `FLOWFORGE_SIGNING_SECRET` is now required. `HmacDevSigning` raises `RuntimeError` at construction if no secret is configured. The hard-coded `"flowforge-dev-secret-not-for-production"` default is gone from the normal code path. Bridge: `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` re-enables it for one minor release with loud-log `WARNING` and Prometheus counter `flowforge_signing_secret_default_used_total`. Run `flowforge pre-upgrade-check signing` in CI before bumping the version.
- **SK-02** (E-34): `HmacDevSigning` accepts a `keys={kid: secret}` map so old signatures verify against their original `key_id` after rotation. `verify(key_id="unknown")` raises `UnknownKeyId` rather than silently failing with the wrong key.
- **SK-03** (E-34): `verify()` returns `True`/`False` for valid/invalid. Unknown key ids raise `UnknownKeyId`; recoverable KMS failures raise `KmsTransientError`. Both AWS and GCP error codes are classified against named frozensets — no string-matching on generic `Exception`.
- **SK-04** (E-56): `AwsKmsSigning` and `GcpKmsSigning` dispatch all blocking SDK calls via `asyncio.to_thread`.

## Compatibility

- Python 3.11+
- `boto3` (optional, `[aws]` extra)
- `google-cloud-kms` (optional, `[gcp]` extra)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-jtbd-hub`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-jtbd-hub) — uses this package to verify manifest signatures at install time
- [`flowforge-cli`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-cli) — `flowforge pre-upgrade-check signing` validates SK-01 readiness
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
