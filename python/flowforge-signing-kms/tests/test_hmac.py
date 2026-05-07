"""Tests for HmacDevSigning — local-dev HMAC-SHA256 backend."""

from __future__ import annotations

import asyncio
import os

import pytest

from flowforge_signing_kms.hmac_dev import HmacDevSigning


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def run(coro):
	loop = asyncio.get_event_loop()
	return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# basic sign / verify
# ---------------------------------------------------------------------------


def test_sign_returns_bytes():
	signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
	sig = run(signer.sign_payload(b"hello"))
	assert isinstance(sig, bytes)
	assert len(sig) == 32  # SHA-256 digest is 32 bytes


def test_verify_valid_signature():
	signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
	payload = b"some workflow payload"
	sig = run(signer.sign_payload(payload))
	assert run(signer.verify(payload, sig, "k1")) is True


def test_verify_wrong_payload_fails():
	signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
	sig = run(signer.sign_payload(b"original"))
	assert run(signer.verify(b"tampered", sig, "k1")) is False


def test_verify_unknown_key_id_raises():
	"""SK-02: verifying with a key_id the signer does not know raises ``UnknownKeyId``.

	Distinct from "wrong signature" so callers can audit the configuration error
	separately from a tampered payload.
	"""
	from flowforge_signing_kms.errors import UnknownKeyId

	signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
	sig = run(signer.sign_payload(b"payload"))
	with pytest.raises(UnknownKeyId):
		run(signer.verify(b"payload", sig, "k2"))


def test_verify_wrong_secret_fails():
	signer_a = HmacDevSigning(secret="secret-a", key_id="k1")
	signer_b = HmacDevSigning(secret="secret-b", key_id="k1")
	sig = run(signer_a.sign_payload(b"payload"))
	assert run(signer_b.verify(b"payload", sig, "k1")) is False


def test_verify_truncated_signature_fails():
	signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
	sig = run(signer.sign_payload(b"payload"))
	assert run(signer.verify(b"payload", sig[:16], "k1")) is False


# ---------------------------------------------------------------------------
# current_key_id
# ---------------------------------------------------------------------------


def test_current_key_id_explicit():
	signer = HmacDevSigning(secret="s3cr3t", key_id="my-key-42")
	assert signer.current_key_id() == "my-key-42"


def test_current_key_id_deterministic():
	signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
	assert signer.current_key_id() == signer.current_key_id()


# ---------------------------------------------------------------------------
# env-var defaults
# ---------------------------------------------------------------------------


def test_env_secret_used_when_no_arg(monkeypatch):
	monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "env-secret")
	monkeypatch.setenv("FLOWFORGE_SIGNING_KEY_ID", "env-key")
	signer = HmacDevSigning()
	assert signer.current_key_id() == "env-key"
	sig = run(signer.sign_payload(b"data"))
	assert run(signer.verify(b"data", sig, "env-key")) is True


def test_no_env_no_arg_raises_runtime_error(monkeypatch):
	"""SK-01: instantiating without secret material raises ``RuntimeError``.

	The hard-coded legacy fallback was removed in E-34.  Operators must
	either pass ``secret=``, set ``FLOWFORGE_SIGNING_SECRET``, or opt in to
	the deprecation flag ``FLOWFORGE_ALLOW_INSECURE_DEFAULT=1``.
	"""
	monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
	monkeypatch.delenv("FLOWFORGE_SIGNING_KEY_ID", raising=False)
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)
	with pytest.raises(RuntimeError, match="explicit secret required"):
		HmacDevSigning()


# ---------------------------------------------------------------------------
# key rotation simulation
# ---------------------------------------------------------------------------


def test_signature_from_old_key_verifiable_via_key_map():
	"""SK-02: rotation via key map keeps the old key id valid for verification.

	Sign with v1, rotate to v2 (carrying both keys in the map), verify the v1
	signature against v1 — succeeds.
	"""
	v1 = HmacDevSigning(keys={"key-v1": "secret-v1"}, current_key_id="key-v1")
	rotated = HmacDevSigning(
		keys={"key-v1": "secret-v1", "key-v2": "secret-v2"},
		current_key_id="key-v2",
	)

	payload = b"important document hash"
	sig_v1 = run(v1.sign_payload(payload))

	assert run(rotated.verify(payload, sig_v1, "key-v1")) is True


def test_new_signatures_isolated_per_key_id():
	"""SK-02: each key id has its own secret; cross-key verifies fail correctly.

	A signature produced under ``key-v2`` does not verify under ``key-v1``
	(both because the key_id is bound into the HMAC input AND because the
	secrets are distinct entries in the key map).
	"""
	signer = HmacDevSigning(
		keys={"key-v1": "secret-v1", "key-v2": "secret-v2"},
		current_key_id="key-v2",
	)
	payload = b"payload"
	sig_v2 = run(signer.sign_payload(payload))
	assert run(signer.verify(payload, sig_v2, "key-v2")) is True
	assert run(signer.verify(payload, sig_v2, "key-v1")) is False


# ---------------------------------------------------------------------------
# protocol compliance
# ---------------------------------------------------------------------------


def test_satisfies_signing_port_protocol():
	"""HmacDevSigning must satisfy the runtime_checkable SigningPort Protocol."""
	from flowforge.ports.signing import SigningPort

	signer = HmacDevSigning(secret="s", key_id="k")
	assert isinstance(signer, SigningPort)
