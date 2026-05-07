"""flowforge-signing-kms — signing adapters for flowforge.

Exports:
    HmacDevSigning      — HMAC-SHA256 local-dev backend (key map, no implicit default)
    AwsKmsSigning       — AWS KMS backend (requires boto3)
    GcpKmsSigning       — GCP Cloud KMS backend (requires google-cloud-kms)

E-34 errors (audit-fix-plan §4.1, §7):
    UnknownKeyId        — verify() called with a key id this signer does not know.
    KmsTransientError   — recoverable KMS failure; caller should retry with backoff.
    KmsSignatureInvalid — KMS reported the signature as permanently invalid.
"""

from flowforge_signing_kms.errors import (
	KmsSignatureInvalid,
	KmsTransientError,
	SigningKmsError,
	UnknownKeyId,
)
from flowforge_signing_kms.hmac_dev import HmacDevSigning
from flowforge_signing_kms.kms import AwsKmsSigning, GcpKmsSigning

__all__ = [
	"HmacDevSigning",
	"AwsKmsSigning",
	"GcpKmsSigning",
	"SigningKmsError",
	"UnknownKeyId",
	"KmsTransientError",
	"KmsSignatureInvalid",
]
