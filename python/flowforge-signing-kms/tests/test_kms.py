"""Tests for AwsKmsSigning and GcpKmsSigning backends.

AWS tests use moto to mock KMS.
GCP tests use a hand-rolled stub (no live GCP needed).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest


def run(coro):
	loop = asyncio.get_event_loop()
	return loop.run_until_complete(coro)


class _NamedError(RuntimeError):
	pass


DeadlineExceeded = type("DeadlineExceeded", (_NamedError,), {})
NotFound = type("NotFound", (_NamedError,), {})


class _AwsClientError(Exception):
	def __init__(self, code: str) -> None:
		super().__init__(code)
		self.response = {"Error": {"Code": code}}


class _AwsStubClient:
	def __init__(self, *, fail: Exception | None = None, valid: bool = True) -> None:
		self.fail = fail
		self.valid = valid

	def _maybe_fail(self) -> None:
		if self.fail is not None:
			raise self.fail

	def generate_mac(self, **kwargs: Any) -> dict[str, bytes]:
		self._maybe_fail()
		return {"Mac": b"aws-mac"}

	def verify_mac(self, **kwargs: Any) -> dict[str, bool]:
		self._maybe_fail()
		return {"MacValid": self.valid}

	def sign(self, **kwargs: Any) -> dict[str, bytes]:
		self._maybe_fail()
		return {"Signature": b"aws-signature"}

	def verify(self, **kwargs: Any) -> dict[str, bool]:
		self._maybe_fail()
		return {"SignatureValid": self.valid}


def _aws_signer(client: _AwsStubClient, *, algorithm: str = "HMAC_SHA_256"):
	from flowforge_signing_kms.kms import AwsKmsSigning

	signer = AwsKmsSigning.__new__(AwsKmsSigning)
	signer._client = client
	signer._key_id = "aws-key"
	signer._algorithm = algorithm
	return signer


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

	def test_verify_unknown_key_id_raises(self):
		"""SK-03 (E-34): unknown key id is a configuration error, not invalid sig.

		Old behavior swallowed the exception and returned False, conflating
		"misconfigured" with "tampered".  New contract surfaces ``UnknownKeyId``
		so callers can audit the difference.
		"""
		import boto3
		from moto import mock_aws
		from flowforge_signing_kms.errors import UnknownKeyId
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
			with pytest.raises(UnknownKeyId):
				run(signer.verify(b"payload", b"garbage-sig", "non-existent-key"))

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


class TestAwsKmsSigningStubbed:
	def test_constructor_uses_endpoint_url_with_injected_boto3(self, monkeypatch):
		import sys
		from types import SimpleNamespace
		from flowforge_signing_kms.kms import AwsKmsSigning

		calls: list[tuple[str, dict[str, Any]]] = []

		def client(service_name: str, **kwargs: Any) -> _AwsStubClient:
			calls.append((service_name, kwargs))
			return _AwsStubClient()

		monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=client))
		signer = AwsKmsSigning("aws-key", endpoint_url="http://localhost:4566")
		assert signer.current_key_id() == "aws-key"
		assert calls == [
			("kms", {"region_name": "us-east-1", "endpoint_url": "http://localhost:4566"})
		]

	def test_constructor_reports_missing_boto3(self, monkeypatch):
		import builtins
		from flowforge_signing_kms.kms import AwsKmsSigning

		real_import = builtins.__import__

		def fake_import(name: str, *args: Any, **kwargs: Any):
			if name == "boto3":
				raise ImportError("missing boto3")
			return real_import(name, *args, **kwargs)

		monkeypatch.setattr(builtins, "__import__", fake_import)
		with pytest.raises(ImportError, match="flowforge-signing-kms\\[aws\\]"):
			AwsKmsSigning("aws-key")

	def test_aws_error_code_falls_back_to_exception_class_name(self):
		from flowforge_signing_kms.kms import _aws_error_code

		assert _aws_error_code(RuntimeError("boom")) == "RuntimeError"
		err = RuntimeError("bad response")
		err.response = {"Error": {"Code": 404}}  # type: ignore[attr-defined]
		assert _aws_error_code(err) == "RuntimeError"
		err.response = {"Error": "not-a-dict"}  # type: ignore[attr-defined]
		assert _aws_error_code(err) == "RuntimeError"

	def test_hmac_sign_and_verify_without_boto(self):
		signer = _aws_signer(_AwsStubClient(valid=True))
		assert run(signer.sign_payload(b"payload")) == b"aws-mac"
		assert run(signer.verify(b"payload", b"aws-mac", "aws-key")) is True

	def test_asymmetric_sign_and_verify_without_boto(self):
		signer = _aws_signer(_AwsStubClient(valid=False), algorithm="RSASSA_PKCS1_V1_5_SHA_256")
		assert run(signer.sign_payload(b"payload")) == b"aws-signature"
		assert run(signer.verify(b"payload", b"aws-signature", "aws-key")) is False

	def test_sign_classifies_transient_and_unknown_key_errors(self):
		from flowforge_signing_kms.errors import KmsTransientError, UnknownKeyId

		with pytest.raises(KmsTransientError):
			run(_aws_signer(_AwsStubClient(fail=_AwsClientError("ThrottlingException"))).sign_payload(b"p"))
		with pytest.raises(UnknownKeyId):
			run(_aws_signer(_AwsStubClient(fail=_AwsClientError("NotFoundException"))).sign_payload(b"p"))

	def test_sign_propagates_unclassified_error(self):
		err = _AwsClientError("ValidationException")
		with pytest.raises(_AwsClientError) as got:
			run(_aws_signer(_AwsStubClient(fail=err)).sign_payload(b"p"))
		assert got.value is err

	def test_verify_classifies_errors_and_returns_false_for_permanent_invalid(self):
		from flowforge_signing_kms.errors import KmsTransientError, UnknownKeyId

		with pytest.raises(KmsTransientError):
			run(_aws_signer(_AwsStubClient(fail=_AwsClientError("InternalServerError"))).verify(b"p", b"s", "aws-key"))
		with pytest.raises(UnknownKeyId):
			run(_aws_signer(_AwsStubClient(fail=_AwsClientError("NoSuchKey"))).verify(b"p", b"s", "aws-key"))
		assert run(_aws_signer(_AwsStubClient(fail=_AwsClientError("KMSInvalidSignatureException"))).verify(b"p", b"s", "aws-key")) is False

	def test_verify_propagates_existing_domain_errors(self):
		from flowforge_signing_kms.errors import KmsTransientError

		with pytest.raises(KmsTransientError):
			run(_aws_signer(_AwsStubClient(fail=KmsTransientError("retry"))).verify(b"p", b"s", "aws-key"))

	def test_sign_propagates_existing_domain_errors(self):
		from flowforge_signing_kms.errors import KmsTransientError

		with pytest.raises(KmsTransientError):
			run(_aws_signer(_AwsStubClient(fail=KmsTransientError("retry"))).sign_payload(b"p"))


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
	def test_constructor_uses_google_kms_client_when_not_injected(self, monkeypatch):
		import sys
		from types import SimpleNamespace
		from flowforge_signing_kms.kms import GcpKmsSigning

		created = _GcpStubClient()
		kms_module = SimpleNamespace(KeyManagementServiceClient=lambda: created)
		google_module = SimpleNamespace()
		cloud_module = SimpleNamespace(kms=kms_module)
		monkeypatch.setitem(sys.modules, "google", google_module)
		monkeypatch.setitem(sys.modules, "google.cloud", cloud_module)
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1")
		assert signer._client is created

	def test_constructor_reports_missing_google_kms(self, monkeypatch):
		import builtins
		from flowforge_signing_kms.kms import GcpKmsSigning

		real_import = builtins.__import__

		def fake_import(name: str, *args: Any, **kwargs: Any):
			if name == "google.cloud":
				raise ImportError("missing google-cloud-kms")
			return real_import(name, *args, **kwargs)

		monkeypatch.setattr(builtins, "__import__", fake_import)
		with pytest.raises(ImportError, match="flowforge-signing-kms\\[gcp\\]"):
			GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1")

	def _make_signer(self, use_mac: bool = True) -> Any:
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

	def test_sign_classifies_transient_and_unknown_key_errors(self):
		from flowforge_signing_kms.errors import KmsTransientError, UnknownKeyId
		from flowforge_signing_kms.kms import GcpKmsSigning

		transient_client = MagicMock()
		transient_client.mac_sign.side_effect = DeadlineExceeded("slow")
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1", use_mac=True, client=transient_client)
		with pytest.raises(KmsTransientError):
			run(signer.sign_payload(b"payload"))

		unknown_client = MagicMock()
		unknown_client.mac_sign.side_effect = NotFound("missing")
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1", use_mac=True, client=unknown_client)
		with pytest.raises(UnknownKeyId):
			run(signer.sign_payload(b"payload"))

	def test_sign_propagates_unclassified_error_and_domain_error(self):
		from flowforge_signing_kms.errors import KmsTransientError
		from flowforge_signing_kms.kms import GcpKmsSigning

		bad_client = MagicMock()
		bad_client.asymmetric_sign.side_effect = RuntimeError("bad request")
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1", client=bad_client)
		with pytest.raises(RuntimeError, match="bad request"):
			run(signer.sign_payload(b"payload"))

		domain_client = MagicMock()
		domain_client.asymmetric_sign.side_effect = KmsTransientError("retry")
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1", client=domain_client)
		with pytest.raises(KmsTransientError):
			run(signer.sign_payload(b"payload"))

	def test_verify_classifies_transient_and_unknown_key_errors(self):
		from flowforge_signing_kms.errors import KmsTransientError, UnknownKeyId
		from flowforge_signing_kms.kms import GcpKmsSigning

		transient_client = MagicMock()
		transient_client.mac_verify.side_effect = DeadlineExceeded("slow")
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1", use_mac=True, client=transient_client)
		with pytest.raises(KmsTransientError):
			run(signer.verify(b"payload", b"sig", signer.current_key_id()))

		unknown_client = MagicMock()
		unknown_client.mac_verify.side_effect = NotFound("missing")
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1", use_mac=True, client=unknown_client)
		with pytest.raises(UnknownKeyId):
			run(signer.verify(b"payload", b"sig", signer.current_key_id()))

	def test_verify_propagates_existing_domain_error(self):
		from flowforge_signing_kms.errors import KmsTransientError
		from flowforge_signing_kms.kms import GcpKmsSigning

		domain_client = MagicMock()
		domain_client.mac_verify.side_effect = KmsTransientError("retry")
		signer = GcpKmsSigning("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1", use_mac=True, client=domain_client)
		with pytest.raises(KmsTransientError):
			run(signer.verify(b"payload", b"sig", signer.current_key_id()))
