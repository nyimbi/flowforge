"""E-34 — Crypto rotation regression tests (SK-01, SK-02, SK-03).

Audit findings:
- SK-01 (P0): No HMAC default secret. ``HmacDevSigning()`` with no
  ``FLOWFORGE_SIGNING_SECRET`` env var raises ``RuntimeError`` unless the opt-in
  ``FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`` is set, which permits with a loud-log warning.
- SK-02 (P1): Per-key_id signed key map. ``HmacDevSigning(keys={...})`` exposes
  multiple key ids; ``verify(key_id="unknown", ...)`` raises ``UnknownKeyId``.
  Pre-rotation signatures verify against pre-rotation key after rotation.
- SK-03 (P1): KMS adapters distinguish ``KmsTransientError`` from
  ``KmsSignatureInvalid``. Transient is retried with backoff; permanent invalid
  returns False.

Plan reference: framework/docs/audit-fix-plan.md §4.1, §7 (E-34).
"""

from __future__ import annotations

import asyncio
import logging

import pytest


def _run(coro):
	loop = asyncio.get_event_loop()
	return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# SK-01 — no default secret (P0)
# ---------------------------------------------------------------------------


def test_SK_01_no_default_secret(monkeypatch):
	"""Instantiating without env var or arg raises RuntimeError."""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)

	with pytest.raises(RuntimeError, match="explicit secret required"):
		HmacDevSigning()


def test_SK_01_explicit_secret_arg_ok(monkeypatch):
	"""Passing secret= explicitly always works regardless of env."""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)

	signer = HmacDevSigning(secret="explicit", key_id="k1")
	assert signer.current_key_id() == "k1"


def test_SK_01_env_secret_used(monkeypatch):
	"""When FLOWFORGE_SIGNING_SECRET is set, no error."""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "env-secret")
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)

	signer = HmacDevSigning()
	sig = _run(signer.sign_payload(b"x"))
	assert _run(signer.verify(b"x", sig, signer.current_key_id())) is True


def test_SK_01_opt_in_allow_insecure_warns(monkeypatch, caplog):
	"""``FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`` permits no-secret start with loud warn."""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
	monkeypatch.setenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", "1")

	with caplog.at_level(logging.WARNING, logger="flowforge_signing_kms.hmac_dev"):
		signer = HmacDevSigning()

	# loud warning emitted
	assert any("INSECURE" in r.message or "insecure" in r.message for r in caplog.records)
	# still functional (so existing dev rigs keep working in deprecation window)
	sig = _run(signer.sign_payload(b"hello"))
	assert _run(signer.verify(b"hello", sig, signer.current_key_id())) is True


def test_SK_01_opt_in_increments_counter(monkeypatch):
	"""Loud-log path also increments observability counter (signoff §10.2)."""
	from flowforge_signing_kms import hmac_dev

	monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
	monkeypatch.setenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", "1")

	before = hmac_dev._INSECURE_DEFAULT_USED_TOTAL
	hmac_dev.HmacDevSigning()
	after = hmac_dev._INSECURE_DEFAULT_USED_TOTAL
	assert after == before + 1


# ---------------------------------------------------------------------------
# SK-02 — key_id rotation map (P1)
# ---------------------------------------------------------------------------


def test_SK_02_key_id_rotation():
	"""Pre-rotation signatures verify against pre-rotation key after rotation."""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	# Stage 1: only key-v1 exists.
	stage1 = HmacDevSigning(keys={"key-v1": "secret-v1"}, current_key_id="key-v1")
	payload = b"important workflow payload"
	sig_v1 = _run(stage1.sign_payload(payload))

	# Stage 2: rotation introduces key-v2; key-v1 retained for verify.
	stage2 = HmacDevSigning(
		keys={"key-v1": "secret-v1", "key-v2": "secret-v2"},
		current_key_id="key-v2",
	)
	sig_v2 = _run(stage2.sign_payload(payload))

	# Pre-rotation sig verifies against pre-rotation key.
	assert _run(stage2.verify(payload, sig_v1, "key-v1")) is True
	# Post-rotation sig verifies against new key.
	assert _run(stage2.verify(payload, sig_v2, "key-v2")) is True
	# And cross-mismatched verify fails (different secret per key_id).
	assert _run(stage2.verify(payload, sig_v1, "key-v2")) is False


def test_SK_02_unknown_key_id_raises():
	"""``verify(key_id="unknown", ...)`` raises ``UnknownKeyId``."""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning
	from flowforge_signing_kms.errors import UnknownKeyId

	signer = HmacDevSigning(keys={"k1": "s1"}, current_key_id="k1")
	sig = _run(signer.sign_payload(b"x"))

	with pytest.raises(UnknownKeyId):
		_run(signer.verify(b"x", sig, "key-that-does-not-exist"))


def test_SK_02_legacy_single_key_form_compat():
	"""Backward-compat: ``HmacDevSigning(secret=..., key_id=...)`` still works.

	The constructor wraps this as a one-entry key map internally.
	"""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
	sig = _run(signer.sign_payload(b"data"))
	assert _run(signer.verify(b"data", sig, "k1")) is True


# ---------------------------------------------------------------------------
# SK-03 — transient vs invalid (P1)
# ---------------------------------------------------------------------------


def test_SK_03_invalid_signature_returns_false():
	"""Permanent invalid (bad signature) → ``verify()`` returns False, no exception."""
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	signer = HmacDevSigning(secret="s", key_id="k1")
	good = _run(signer.sign_payload(b"x"))
	# Tamper bytes — should be a permanent invalid → False, not an exception.
	assert _run(signer.verify(b"x", good[:-1] + b"\x00", "k1")) is False


def test_SK_03_transient_distinct_from_invalid():
	"""``KmsTransientError`` is a distinct type from ``KmsSignatureInvalid``."""
	from flowforge_signing_kms.errors import (
		KmsSignatureInvalid,
		KmsTransientError,
	)

	# Both inherit from a common base but are NOT subclasses of each other.
	assert KmsTransientError is not KmsSignatureInvalid
	assert not issubclass(KmsTransientError, KmsSignatureInvalid)
	assert not issubclass(KmsSignatureInvalid, KmsTransientError)


def test_SK_03_aws_transient_raises_transient_error():
	"""AWS adapter: simulated network/throttling exception → ``KmsTransientError``.

	Permanent ``Invalid*`` exceptions remain ``return False``.
	"""
	from flowforge_signing_kms.errors import KmsTransientError
	from flowforge_signing_kms.kms import AwsKmsSigning

	# Inject a stub client that raises a botocore-style throttling error.
	class _ThrottledClient:
		def generate_mac(self, **_):
			raise _BotoStub("ThrottlingException", "rate exceeded")

		def verify_mac(self, **_):
			raise _BotoStub("ThrottlingException", "rate exceeded")

	signer = AwsKmsSigning.__new__(AwsKmsSigning)  # bypass boto3 import-guard
	signer._client = _ThrottledClient()  # type: ignore[attr-defined]
	signer._key_id = "alias/test"
	signer._algorithm = "HMAC_SHA_256"

	with pytest.raises(KmsTransientError):
		_run(signer.verify(b"x", b"sig", "alias/test"))


def test_SK_03_aws_permanent_invalid_returns_false():
	"""AWS adapter: KMS reporting MAC invalid (no exception) → return False."""
	from flowforge_signing_kms.kms import AwsKmsSigning

	class _InvalidClient:
		def verify_mac(self, **_):
			return {"MacValid": False}

	signer = AwsKmsSigning.__new__(AwsKmsSigning)
	signer._client = _InvalidClient()  # type: ignore[attr-defined]
	signer._key_id = "alias/test"
	signer._algorithm = "HMAC_SHA_256"

	assert _run(signer.verify(b"x", b"sig", "alias/test")) is False


def test_SK_03_aws_unknown_key_raises_unknown_key_id():
	"""AWS adapter: NotFoundException → ``UnknownKeyId`` (not a transient retry)."""
	from flowforge_signing_kms.errors import UnknownKeyId
	from flowforge_signing_kms.kms import AwsKmsSigning

	class _NotFoundClient:
		def verify_mac(self, **_):
			raise _BotoStub("NotFoundException", "Key 'alias/missing' does not exist")

	signer = AwsKmsSigning.__new__(AwsKmsSigning)
	signer._client = _NotFoundClient()  # type: ignore[attr-defined]
	signer._key_id = "alias/missing"
	signer._algorithm = "HMAC_SHA_256"

	with pytest.raises(UnknownKeyId):
		_run(signer.verify(b"x", b"sig", "alias/missing"))


# ---------------------------------------------------------------------------
# stub: minimal botocore-style ClientError for SK-03 transient detection
# ---------------------------------------------------------------------------


class _BotoStub(Exception):
	"""Stand-in for ``botocore.exceptions.ClientError`` carrying the same shape."""

	def __init__(self, code: str, message: str) -> None:
		super().__init__(f"{code}: {message}")
		self.response = {"Error": {"Code": code, "Message": message}}
