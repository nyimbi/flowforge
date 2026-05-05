"""Tests for AwsKmsSigning and GcpKmsSigning backends.

AWS tests use moto to mock KMS.
GCP tests use a hand-rolled stub (no live GCP needed).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


def run(coro):
	loop = asyncio.get_event_loop()
	return loop.run_until_complete(coro)


# ===========================================================================
# AWS KMS tests (moto)
# ===========================================================================


def _boto3_available() -> bool:
	try:
		import boto3  # noqa: F401
		return True
	except ImportError:
		return False


def _moto_available() -> bool:
	try:
		import moto  # noqa: F401
		return True
	except ImportError:
		return False


aws_required = pytest.mark.skipif(
	not (_boto3_available() and _moto_available()),
	reason="boto3 and moto required for AWS KMS tests",
)


@aws_required
class TestAwsKmsSigning:
	"""AWS KMS signing tests using moto mock."""

	def _make_signer(self):
		"""Create a moto-backed AwsKmsSigning instance with a real HMAC key."""
		import boto3
		from moto import mock_aws
		from flowforge_signing_kms.kms import AwsKmsSigning

		with mock_aws():
			client = boto3.client("kms", region_name="us-east-1")
			key_resp = client.create_key(
				Description="test-hmac-key",
				KeyUsage="GENERATE_VERIFY_MAC",
				KeySpec="HMAC_256",
			)
			key_id = key_resp["KeyMetadata"]["KeyId"]
			return mock_aws, key_id

	def test_sign_and_verify(self):
		import boto3
		from moto import mock_aws
		from flowforge_signing_kms.kms import AwsKmsSigning

		with mock_aws():
			client = boto3.client("kms", region_name="us-east-1")
			key_resp = client.create_key(
				Description="test-hmac-key",
				KeyUsage="GENERATE_VERIFY_MAC",
				KeySpec="HMAC_256",
			)
			key_id = key_resp["KeyMetadata"]["KeyId"]
			signer = AwsKmsSigning(key_id=key_id, region_name="us-east-1")
			payload = b"flowforge workflow payload"
			sig = run(signer.sign_payload(payload))
			assert isinstance(sig, bytes)
			assert len(sig) > 0
			result = run(signer.verify(payload, sig, key_id))
			assert result is True

	def test_verify_tampered_payload_fails(self):
		import boto3
		from moto import mock_aws
		from flowforge_signing_kms.kms import AwsKmsSigning

		with mock_aws():
			client = boto3.client("kms", region_name="us-east-1")
			key_resp = client.create_key(
				Description="test-hmac-key",
				KeyUsage="GENERATE_VERIFY_MAC",
				KeySpec="HMAC_256",
			)
			key_id = key_resp["KeyMetadata"]["KeyId"]
			signer = AwsKmsSigning(key_id=key_id, region_name="us-east-1")
			sig = run(signer.sign_payload(b"original"))
			result = run(signer.verify(b"tampered", sig, key_id))
			assert result is False

	def test_current_key_id_returns_arn_or_alias(self):
		import boto3
		from moto import mock_aws
		from flowforge_signing_kms.kms import AwsKmsSigning

		with mock_aws():
			client = boto3.client("kms", region_name="us-east-1")
			key_resp = client.create_key(
				Description="test",
				KeyUsage="GENERATE_VERIFY_MAC",
				KeySpec="HMAC_256",
			)
			key_id = key_resp["KeyMetadata"]["KeyId"]
			signer = AwsKmsSigning(key_id=key_id, region_name="us-east-1")
			assert signer.current_key_id() == key_id

	def test_verify_returns_false_on_exception(self):
		import boto3
		from moto import mock_aws
		from flowforge_signing_kms.kms import AwsKmsSigning

		with mock_aws():
			client = boto3.client("kms", region_name="us-east-1")
			key_resp = client.create_key(
				Description="test",
				KeyUsage="GENERATE_VERIFY_MAC",
				KeySpec="HMAC_256",
			)
			key_id = key_resp["KeyMetadata"]["KeyId"]
			signer = AwsKmsSigning(key_id=key_id, region_name="us-east-1")
			# pass garbage key_id -> KMS will raise -> verify returns False
			result = run(signer.verify(b"payload", b"garbage-sig", "non-existent-key"))
			assert result is False

	def test_satisfies_signing_port_protocol(self):
		import boto3
		from moto import mock_aws
		from flowforge.ports.signing import SigningPort
		from flowforge_signing_kms.kms import AwsKmsSigning

		with mock_aws():
			client = boto3.client("kms", region_name="us-east-1")
			key_resp = client.create_key(
				Description="test",
				KeyUsage="GENERATE_VERIFY_MAC",
				KeySpec="HMAC_256",
			)
			key_id = key_resp["KeyMetadata"]["KeyId"]
			signer = AwsKmsSigning(key_id=key_id, region_name="us-east-1")
			assert isinstance(signer, SigningPort)


# ===========================================================================
# GCP KMS tests (stub client)
# ===========================================================================


class _GcpMacSignResponse:
	def __init__(self, mac: bytes) -> None:
		self.mac = mac


class _GcpMacVerifyResponse:
	def __init__(self, success: bool) -> None:
		self.success = success


class _GcpStubClient:
	"""Minimal GCP KMS client stub for testing GcpKmsSigning without live GCP."""

	def __init__(self, secret: bytes = b"gcp-stub-secret") -> None:
		import hashlib
		import hmac as _hmac
		self._secret = secret

	def _mac(self, data: bytes) -> bytes:
		import hashlib
		import hmac as _hmac
		return _hmac.new(self._secret, data, hashlib.sha256).digest()

	def mac_sign(self, request: dict) -> _GcpMacSignResponse:
		return _GcpMacSignResponse(mac=self._mac(request["data"]))

	def mac_verify(self, request: dict) -> _GcpMacVerifyResponse:
		import hmac as _hmac
		expected = self._mac(request["data"])
		ok = _hmac.compare_digest(expected, request["mac"])
		return _GcpMacVerifyResponse(success=ok)

	def asymmetric_sign(self, request: dict) -> MagicMock:
		resp = MagicMock()
		resp.signature = self._mac(request["digest"]["sha256"])
		return resp

	def asymmetric_verify(self, request: dict) -> MagicMock:
		import hmac as _hmac
		expected = self._mac(request["digest"]["sha256"])
		resp = MagicMock()
		resp.success = _hmac.compare_digest(expected, request["signature"])
		return resp


class TestGcpKmsSigning:
	def _make_signer(self, use_mac: bool = True) -> object:
		from flowforge_signing_kms.kms import GcpKmsSigning

		stub = _GcpStubClient()
		return GcpKmsSigning(
			key_version_name="projects/p/locations/global/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1",
			use_mac=use_mac,
			client=stub,
		)

	def test_mac_sign_returns_bytes(self):
		signer = self._make_signer(use_mac=True)
		sig = run(signer.sign_payload(b"test payload"))
		assert isinstance(sig, bytes)
		assert len(sig) == 32

	def test_mac_sign_verify_roundtrip(self):
		signer = self._make_signer(use_mac=True)
		payload = b"workflow state hash"
		sig = run(signer.sign_payload(payload))
		key_id = signer.current_key_id()
		assert run(signer.verify(payload, sig, key_id)) is True

	def test_mac_verify_tampered_fails(self):
		signer = self._make_signer(use_mac=True)
		sig = run(signer.sign_payload(b"original"))
		key_id = signer.current_key_id()
		assert run(signer.verify(b"tampered", sig, key_id)) is False

	def test_asymmetric_sign_verify_roundtrip(self):
		signer = self._make_signer(use_mac=False)
		payload = b"asymmetric payload"
		sig = run(signer.sign_payload(payload))
		key_id = signer.current_key_id()
		assert run(signer.verify(payload, sig, key_id)) is True

	def test_asymmetric_verify_tampered_fails(self):
		signer = self._make_signer(use_mac=False)
		sig = run(signer.sign_payload(b"good payload"))
		key_id = signer.current_key_id()
		assert run(signer.verify(b"bad payload", sig, key_id)) is False

	def test_current_key_id(self):
		from flowforge_signing_kms.kms import GcpKmsSigning

		kvn = "projects/p/locations/global/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1"
		signer = GcpKmsSigning(key_version_name=kvn, client=_GcpStubClient())
		assert signer.current_key_id() == kvn

	def test_verify_exception_returns_false(self):
		from flowforge_signing_kms.kms import GcpKmsSigning

		bad_client = MagicMock()
		bad_client.mac_sign.side_effect = RuntimeError("network error")
		bad_client.mac_verify.side_effect = RuntimeError("network error")

		signer = GcpKmsSigning(
			key_version_name="projects/p/locations/x/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1",
			use_mac=True,
			client=bad_client,
		)
		result = run(signer.verify(b"payload", b"sig", "key"))
		assert result is False

	def test_satisfies_signing_port_protocol(self):
		from flowforge.ports.signing import SigningPort
		from flowforge_signing_kms.kms import GcpKmsSigning

		signer = GcpKmsSigning(
			key_version_name="projects/p/locations/global/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1",
			client=_GcpStubClient(),
		)
		assert isinstance(signer, SigningPort)
