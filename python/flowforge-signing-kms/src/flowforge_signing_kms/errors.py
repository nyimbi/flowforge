"""Exception types for flowforge-signing-kms (E-34, finding SK-02 + SK-03).

Three concerns:

* ``UnknownKeyId`` (SK-02) — caller asked to verify against a key id that the
  signer has never been told about.  Distinct from "valid key but invalid
  signature" so callers can surface a precise audit event.
* ``KmsTransientError`` (SK-03) — KMS call failed for an infrastructural reason
  (network, throttling, dependency timeout).  Caller should retry with backoff.
* ``KmsSignatureInvalid`` (SK-03) — KMS reported the signature as invalid.
  This is a permanent decision; ``verify()`` returns ``False`` rather than
  raising so the call site stays branch-friendly.

Reference: framework/docs/audit-fix-plan.md §4.1, §7 (E-34).
"""

from __future__ import annotations


class SigningKmsError(Exception):
	"""Base class for all flowforge-signing-kms exceptions."""


class UnknownKeyId(SigningKmsError):
	"""Caller passed a ``key_id`` the signer has no secret/handle for.

	Raised by ``HmacDevSigning.verify`` when the key id is not in the configured
	key map, and by KMS adapters when the cloud provider reports the key id
	does not exist (e.g. AWS ``NotFoundException``, GCP ``NOT_FOUND``).
	"""


class KmsTransientError(SigningKmsError):
	"""Transient KMS failure — caller should retry with backoff.

	Indicates a recoverable infrastructure condition: throttling, network
	error, dependency timeout, internal server error.  Not a permanent
	signature-invalid signal.
	"""


class KmsSignatureInvalid(SigningKmsError):
	"""KMS reported the signature is invalid.

	Surfaced as a distinct type for callers that want to log specifically.
	The standard ``verify()`` path catches this and returns ``False`` so the
	common code path stays branch-friendly; raise it from custom code if you
	need to differentiate from "transient failure".
	"""
