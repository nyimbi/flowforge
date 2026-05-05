# flowforge-signing-kms changelog

## 0.1.0 (2026-05-05)

- `HmacDevSigning`: HMAC-SHA256 local-dev backend with env-var secret and key rotation support.
- `AwsKmsSigning`: AWS KMS adapter (HMAC_SHA_256 or asymmetric RSA), tested via moto.
- `GcpKmsSigning`: GCP Cloud KMS adapter (MAC or asymmetric RSA), tested via stub client.
- All three satisfy the `SigningPort` protocol from `flowforge.ports.signing`.
