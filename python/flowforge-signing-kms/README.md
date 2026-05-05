# flowforge-signing-kms

Signing adapters for the flowforge `SigningPort` protocol. Three backends:

- **HmacDevSigning** — HMAC-SHA256, reads secret from `FLOWFORGE_SIGNING_SECRET` env var. For local development only.
- **AwsKmsSigning** — AWS KMS (HMAC or asymmetric RSA). Requires `boto3`.
- **GcpKmsSigning** — GCP Cloud KMS (MAC or asymmetric RSA). Requires `google-cloud-kms`.

## Install

```bash
# base (HmacDevSigning only)
pip install flowforge-signing-kms

# with AWS KMS support
pip install "flowforge-signing-kms[aws]"

# with GCP KMS support
pip install "flowforge-signing-kms[gcp]"
```

## Usage

```python
from flowforge_signing_kms import HmacDevSigning, AwsKmsSigning, GcpKmsSigning

# local dev
signer = HmacDevSigning(secret="my-secret", key_id="key-v1")
sig = await signer.sign_payload(b"payload")
ok = await signer.verify(b"payload", sig, signer.current_key_id())

# AWS KMS (moto-compatible in tests)
signer = AwsKmsSigning(key_id="alias/my-key", region_name="us-east-1")

# GCP KMS (inject a stub client in tests)
signer = GcpKmsSigning(
    key_version_name="projects/p/locations/global/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1",
    use_mac=True,
)
```

## Testing

```bash
pip install "flowforge-signing-kms[dev]"
pytest tests/
```

AWS tests use `moto` for KMS mocking. GCP tests use an in-process stub — no live GCP required.
