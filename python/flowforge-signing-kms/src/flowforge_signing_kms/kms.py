"""AWS KMS and GCP Cloud KMS signing adapters.

Both classes implement the ``SigningPort`` protocol from ``flowforge.ports.signing``.

Import guards ensure the optional dependencies (boto3 / google-cloud-kms) are only
required when the respective class is actually instantiated, keeping the base install
light.

E-34 SK-03 hardening (audit-fix-plan §4.1, §7):

* ``KmsTransientError`` — raised when KMS reports a recoverable failure
  (throttling, network error, internal error).  Caller is expected to retry
  with backoff.
* ``KmsSignatureInvalid`` — declared for callers that want to differentiate
  "permanent invalid" from "transient".  ``verify()`` itself returns ``False``
  for permanent invalid (branch-friendly default).
* ``UnknownKeyId`` — raised when KMS reports the key id does not exist; this
  is a configuration error, not a "tampered signature".
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from flowforge_signing_kms.errors import (
	KmsSignatureInvalid as KmsSignatureInvalid,  # re-export for callers
	KmsTransientError,
	UnknownKeyId,
)

if TYPE_CHECKING:
	pass  # kept for future type-only imports

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AWS error classification (SK-03)
# ---------------------------------------------------------------------------


# AWS error codes that indicate a *transient* condition — caller should retry.
_AWS_TRANSIENT_CODES: frozenset[str] = frozenset(
	{
		"ThrottlingException",
		"Throttling",
		"RequestLimitExceeded",
		"InternalServerError",
		"InternalFailure",
		"ServiceUnavailable",
		"KMSInternalException",
		"DependencyTimeoutException",
		"RequestTimeout",
		"RequestTimeoutException",
	}
)

# AWS error codes that indicate the key_id is unknown.
_AWS_UNKNOWN_KEY_CODES: frozenset[str] = frozenset(
	{
		"NotFoundException",
		"NoSuchKey",
	}
)


def _aws_error_code(exc: Exception) -> str | None:
	"""Best-effort extraction of an AWS error code from a botocore-style exception."""
	resp = getattr(exc, "response", None)
	if isinstance(resp, dict):
		err = resp.get("Error")
		if isinstance(err, dict):
			code = err.get("Code")
			if isinstance(code, str):
				return code
	# Fall back: some error classes carry their AWS code as attribute name.
	return type(exc).__name__


def _aws_classify(exc: Exception) -> Exception:
	"""Map a raw AWS exception to one of our domain types.

	Returns:
		``KmsTransientError`` for retryable infra failures,
		``UnknownKeyId`` for "key not found",
		otherwise the original exception (caller treats as permanent invalid).
	"""
	code = _aws_error_code(exc)
	if code in _AWS_TRANSIENT_CODES:
		return KmsTransientError(f"AWS KMS transient error: {code}: {exc}")
	if code in _AWS_UNKNOWN_KEY_CODES:
		return UnknownKeyId(f"AWS KMS reports unknown key: {code}: {exc}")
	return exc


# ---------------------------------------------------------------------------
# GCP error classification (SK-03)
# ---------------------------------------------------------------------------


# google.api_core.exceptions class names that indicate a transient condition.
_GCP_TRANSIENT_NAMES: frozenset[str] = frozenset(
	{
		"DeadlineExceeded",
		"InternalServerError",
		"ServiceUnavailable",
		"TooManyRequests",
		"ResourceExhausted",
		"Aborted",
		"RetryError",
	}
)

_GCP_UNKNOWN_NAMES: frozenset[str] = frozenset(
	{
		"NotFound",
	}
)


def _gcp_classify(exc: Exception) -> Exception:
	"""Map a raw GCP exception to one of our domain types."""
	name = type(exc).__name__
	if name in _GCP_TRANSIENT_NAMES:
		return KmsTransientError(f"GCP KMS transient error: {name}: {exc}")
	if name in _GCP_UNKNOWN_NAMES:
		return UnknownKeyId(f"GCP KMS reports unknown key: {name}: {exc}")
	return exc


# ---------------------------------------------------------------------------
# AWS KMS adapter
# ---------------------------------------------------------------------------


class AwsKmsSigning:
	"""AWS KMS signing adapter.

	Uses ``SIGN`` + ``VERIFY`` KMS operations with the
	``RSASSA_PKCS1_V1_5_SHA_256`` algorithm (asymmetric) **or** an HMAC key
	(``HMAC_SHA_256``) depending on *algorithm*.

	For integration tests this class works transparently with *moto*'s KMS
	mock — just start the mock before constructing the instance.

	Parameters
	----------
	key_id:
	    AWS KMS key ARN or alias (e.g. ``"alias/my-signing-key"``).
	region_name:
	    AWS region.  Defaults to ``"us-east-1"``.
	algorithm:
	    KMS signing algorithm.  Defaults to ``"HMAC_SHA_256"`` (symmetric,
	    works with moto out-of-the-box).
	endpoint_url:
	    Override KMS endpoint (useful for local stacks / moto server mode).
	"""

	def __init__(
		self,
		key_id: str,
		region_name: str = "us-east-1",
		algorithm: str = "HMAC_SHA_256",
		endpoint_url: str | None = None,
	) -> None:
		try:
			import boto3  # type: ignore[import-untyped]
		except ImportError as exc:
			raise ImportError(
				"boto3 is required for AwsKmsSigning.  "
				"Install it with: pip install flowforge-signing-kms[aws]"
			) from exc

		kwargs: dict = {"region_name": region_name}
		if endpoint_url is not None:
			kwargs["endpoint_url"] = endpoint_url

		self._client = boto3.client("kms", **kwargs)
		self._key_id = key_id
		self._algorithm = algorithm

	# ------------------------------------------------------------------
	# SigningPort protocol
	# ------------------------------------------------------------------

	async def sign_payload(self, payload: bytes) -> bytes:
		"""Sign *payload* with AWS KMS and return the raw signature bytes.

		E-56 / SK-04: the blocking ``boto3`` client call is dispatched
		via :func:`asyncio.to_thread` so it does not stall the event
		loop during the ~50–500 ms KMS round-trip.

		Transient errors are re-raised as ``KmsTransientError`` (SK-03) so
		callers can retry with backoff.
		"""
		try:
			if self._algorithm.startswith("HMAC"):
				resp = await asyncio.to_thread(
					self._client.generate_mac,
					KeyId=self._key_id,
					Message=payload,
					MacAlgorithm=self._algorithm,
				)
				return resp["Mac"]
			else:
				resp = await asyncio.to_thread(
					self._client.sign,
					KeyId=self._key_id,
					Message=payload,
					MessageType="RAW",
					SigningAlgorithm=self._algorithm,
				)
				return resp["Signature"]
		except (KmsTransientError, UnknownKeyId):
			raise
		except Exception as exc:
			classified = _aws_classify(exc)
			if classified is exc:
				raise
			raise classified from exc

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		"""Verify *signature* against *payload* via AWS KMS.

		E-56 / SK-04: blocking ``boto3`` call dispatched via
		:func:`asyncio.to_thread`.

		Error classification (SK-03):

		* Transient failures (throttling, network, internal errors) re-raise
		  as ``KmsTransientError`` so callers can retry with backoff.
		* Unknown key_id re-raises as ``UnknownKeyId``.
		* Permanent "signature invalid" responses return ``False``.
		"""
		try:
			if self._algorithm.startswith("HMAC"):
				resp = await asyncio.to_thread(
					self._client.verify_mac,
					KeyId=key_id,
					Message=payload,
					Mac=signature,
					MacAlgorithm=self._algorithm,
				)
				return bool(resp.get("MacValid", False))
			else:
				resp = await asyncio.to_thread(
					self._client.verify,
					KeyId=key_id,
					Message=payload,
					MessageType="RAW",
					Signature=signature,
					SigningAlgorithm=self._algorithm,
				)
				return bool(resp.get("SignatureValid", False))
		except (KmsTransientError, UnknownKeyId):
			# Already a domain error — propagate.
			raise
		except Exception as exc:  # pragma: no cover - boto3 specific paths
			classified = _aws_classify(exc)
			if isinstance(classified, (KmsTransientError, UnknownKeyId)):
				raise classified from exc
			# Permanent invalid (e.g. KMSInvalidSignatureException) → False.
			_logger.debug("AWS KMS verify returned False due to %s: %s", type(exc).__name__, exc)
			return False

	def current_key_id(self) -> str:
		"""Return the AWS KMS key id / ARN configured at construction time."""
		return self._key_id


# ---------------------------------------------------------------------------
# GCP Cloud KMS adapter
# ---------------------------------------------------------------------------


class GcpKmsSigning:
	"""GCP Cloud KMS signing adapter.

	Uses the ``AsymmetricSign`` / ``AsymmetricVerify`` RPCs for
	``RSA_SIGN_PKCS1_2048_SHA256`` key versions, or ``MacSign`` /
	``MacVerify`` for HMAC keys.

	Parameters
	----------
	key_version_name:
	    Full GCP KMS resource name, e.g.
	    ``"projects/p/locations/global/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1"``.
	use_mac:
	    When ``True``, use MAC operations (HMAC key).  Default ``False``
	    (asymmetric RSA sign/verify).
	client:
	    Optional pre-constructed ``KeyManagementServiceClient``.  Inject a
	    mock in tests.
	"""

	def __init__(
		self,
		key_version_name: str,
		use_mac: bool = False,
		client: Any | None = None,
	) -> None:
		if client is None:
			try:
				from google.cloud import kms  # type: ignore[import-untyped]
			except ImportError as exc:
				raise ImportError(
					"google-cloud-kms is required for GcpKmsSigning.  "
					"Install it with: pip install flowforge-signing-kms[gcp]"
				) from exc
			self._client: Any = kms.KeyManagementServiceClient()
		else:
			self._client = client

		self._key_version_name = key_version_name
		self._use_mac = use_mac

	# ------------------------------------------------------------------
	# SigningPort protocol
	# ------------------------------------------------------------------

	async def sign_payload(self, payload: bytes) -> bytes:
		"""Sign *payload* with GCP KMS and return the raw signature bytes.

		E-56 / SK-04: blocking ``google-cloud-kms`` call dispatched via
		:func:`asyncio.to_thread` so the event loop stays responsive
		during the gRPC round-trip.

		Transient errors are re-raised as ``KmsTransientError`` (SK-03).
		"""
		try:
			if self._use_mac:
				response = await asyncio.to_thread(
					self._client.mac_sign,
					request={
						"name": self._key_version_name,
						"data": payload,
					},
				)
				return bytes(response.mac)
			else:
				import hashlib

				digest = hashlib.sha256(payload).digest()
				response = await asyncio.to_thread(
					self._client.asymmetric_sign,
					request={
						"name": self._key_version_name,
						"digest": {"sha256": digest},
					},
				)
				return bytes(response.signature)
		except (KmsTransientError, UnknownKeyId):
			raise
		except Exception as exc:
			classified = _gcp_classify(exc)
			if classified is exc:
				raise
			raise classified from exc

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		"""Verify *signature* against *payload* via GCP KMS.

		E-56 / SK-04: blocking gRPC call dispatched via
		:func:`asyncio.to_thread`.

		Error classification (SK-03):

		* Transient (Deadline, Unavailable, ResourceExhausted, etc.) →
		  ``KmsTransientError``.
		* ``NotFound`` (unknown key) → ``UnknownKeyId``.
		* Permanent invalid → ``False``.
		"""
		try:
			if self._use_mac:
				response = await asyncio.to_thread(
					self._client.mac_verify,
					request={
						"name": key_id,
						"data": payload,
						"mac": signature,
					},
				)
				return bool(response.success)
			else:
				import hashlib

				digest = hashlib.sha256(payload).digest()
				response = await asyncio.to_thread(
					self._client.asymmetric_verify,
					request={
						"name": key_id,
						"digest": {"sha256": digest},
						"signature": signature,
					},
				)
				return bool(response.success)
		except (KmsTransientError, UnknownKeyId):
			raise
		except Exception as exc:
			classified = _gcp_classify(exc)
			if isinstance(classified, (KmsTransientError, UnknownKeyId)):
				raise classified from exc
			_logger.debug(
				"GCP KMS verify returned False due to %s: %s", type(exc).__name__, exc
			)
			return False

	def current_key_id(self) -> str:
		"""Return the GCP KMS key version name configured at construction."""
		return self._key_version_name
