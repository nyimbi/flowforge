"""AWS KMS and GCP Cloud KMS signing adapters.

Both classes implement the ``SigningPort`` protocol from ``flowforge.ports.signing``.

Import guards ensure the optional dependencies (boto3 / google-cloud-kms) are only
required when the respective class is actually instantiated, keeping the base install
light.
"""

from __future__ import annotations

import base64
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
	pass  # kept for future type-only imports


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
		"""Sign *payload* with AWS KMS and return the raw signature bytes."""
		if self._algorithm.startswith("HMAC"):
			resp = self._client.generate_mac(
				KeyId=self._key_id,
				Message=payload,
				MacAlgorithm=self._algorithm,
			)
			return resp["Mac"]
		else:
			resp = self._client.sign(
				KeyId=self._key_id,
				Message=payload,
				MessageType="RAW",
				SigningAlgorithm=self._algorithm,
			)
			return resp["Signature"]

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		"""Verify *signature* against *payload* via AWS KMS."""
		try:
			if self._algorithm.startswith("HMAC"):
				resp = self._client.verify_mac(
					KeyId=key_id,
					Message=payload,
					Mac=signature,
					MacAlgorithm=self._algorithm,
				)
				return bool(resp.get("MacValid", False))
			else:
				resp = self._client.verify(
					KeyId=key_id,
					Message=payload,
					MessageType="RAW",
					Signature=signature,
					SigningAlgorithm=self._algorithm,
				)
				return bool(resp.get("SignatureValid", False))
		except Exception:
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
		"""Sign *payload* with GCP KMS and return the raw signature bytes."""
		if self._use_mac:
			response = self._client.mac_sign(
				request={
					"name": self._key_version_name,
					"data": payload,
				}
			)
			return bytes(response.mac)
		else:
			import hashlib

			digest = hashlib.sha256(payload).digest()
			response = self._client.asymmetric_sign(
				request={
					"name": self._key_version_name,
					"digest": {"sha256": digest},
				}
			)
			return bytes(response.signature)

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		"""Verify *signature* against *payload* via GCP KMS."""
		try:
			if self._use_mac:
				response = self._client.mac_verify(
					request={
						"name": key_id,
						"data": payload,
						"mac": signature,
					}
				)
				return bool(response.success)
			else:
				import hashlib

				digest = hashlib.sha256(payload).digest()
				response = self._client.asymmetric_verify(
					request={
						"name": key_id,
						"digest": {"sha256": digest},
						"signature": signature,
					}
				)
				return bool(response.success)
		except Exception:
			return False

	def current_key_id(self) -> str:
		"""Return the GCP KMS key version name configured at construction."""
		return self._key_version_name
