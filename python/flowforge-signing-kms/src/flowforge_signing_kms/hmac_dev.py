"""HmacDevSigning — local-dev signing backend using HMAC-SHA256.

E-34 hardening (audit-fix-plan §4.1, §7):

* SK-01 — no implicit default secret.  Instantiating without
  ``FLOWFORGE_SIGNING_SECRET`` env var (or an explicit ``secret=`` /
  ``keys=`` argument) raises ``RuntimeError``.  Operators may opt in to the
  legacy default for one minor-version deprecation window by setting
  ``FLOWFORGE_ALLOW_INSECURE_DEFAULT=1``; doing so emits a loud-log
  ``WARNING`` and increments ``_INSECURE_DEFAULT_USED_TOTAL`` (mirrored to
  the Prometheus metric ``flowforge_signing_secret_default_used_total``).
* SK-02 — per-key_id signed key map.  ``HmacDevSigning(keys={kid: secret})``
  configures the signer with multiple keys; ``verify(key_id="unknown", ...)``
  raises ``UnknownKeyId`` rather than silently using the wrong secret.  Old
  signatures verify against their original ``key_id`` after rotation.
* SK-03 — ``verify`` only returns ``True``/``False`` for valid-vs-invalid;
  unknown key ids surface as ``UnknownKeyId`` so callers can distinguish
  "wrong configuration" from "tampered signature".

Not for production use.  See ``AwsKmsSigning`` / ``GcpKmsSigning`` for the
production paths.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Final

from flowforge_signing_kms.errors import UnknownKeyId

_logger = logging.getLogger(__name__)

# Sentinel secret used only when the operator explicitly opts in via
# ``FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`` during the deprecation window.
_LEGACY_DEFAULT_SECRET: Final = "flowforge-dev-secret-not-for-production"
_LEGACY_DEFAULT_KEY_ID: Final = "dev-key-1"
_SEP: Final = b"."

# Process-wide counter mirrored by the Prometheus collector
# ``flowforge_signing_secret_default_used_total`` (audit-fix-plan §10.2).
_INSECURE_DEFAULT_USED_TOTAL: int = 0


def _hmac_sign(secret: str, key_id: str, payload: bytes) -> bytes:
	"""Return raw HMAC-SHA256 digest over ``key_id + "." + payload``."""
	msg = key_id.encode() + _SEP + payload
	return hmac.new(secret.encode(), msg, hashlib.sha256).digest()


def _resolve_keys(
	secret: str | None,
	key_id: str | None,
	keys: dict[str, str] | None,
	current_key_id: str | None,
) -> tuple[dict[str, str], str]:
	"""Reconcile the three constructor forms into ``(keys_map, current_key_id)``.

	Forms accepted:

	* ``HmacDevSigning(secret="s", key_id="k1")`` — legacy single-key form.
	  Wrapped as ``{"k1": "s"}`` with current ``"k1"``.  ``key_id`` defaults
	  to ``$FLOWFORGE_SIGNING_KEY_ID`` then ``"dev-key-1"``.
	* ``HmacDevSigning(keys={...}, current_key_id="k2")`` — explicit map.
	* ``HmacDevSigning()`` (env-only) — read ``$FLOWFORGE_SIGNING_SECRET``
	  and ``$FLOWFORGE_SIGNING_KEY_ID``.  Raises ``RuntimeError`` if no
	  secret material is available unless ``$FLOWFORGE_ALLOW_INSECURE_DEFAULT=1``
	  is set.
	"""
	# Forbid mixing the two forms — easier to misconfigure than helpful.
	if keys is not None and (secret is not None or key_id is not None):
		raise ValueError(
			"HmacDevSigning: pass either (secret=, key_id=) OR (keys=, current_key_id=), not both"
		)

	if keys is not None:
		assert isinstance(keys, dict), "keys must be dict[str,str]"
		assert all(isinstance(k, str) and isinstance(v, str) for k, v in keys.items()), (
			"keys map entries must be (str, str)"
		)
		if not keys:
			raise ValueError("HmacDevSigning(keys=...) cannot be empty")
		if current_key_id is None:
			raise ValueError(
				"HmacDevSigning(keys=...): current_key_id= must name an entry"
			)
		if current_key_id not in keys:
			raise ValueError(
				f"HmacDevSigning(keys=...): current_key_id={current_key_id!r} not in keys"
			)
		return dict(keys), current_key_id

	# Legacy single-key form.
	env_secret = os.environ.get("FLOWFORGE_SIGNING_SECRET")
	env_key_id = os.environ.get("FLOWFORGE_SIGNING_KEY_ID")

	resolved_secret = secret if secret is not None else env_secret
	resolved_key_id = key_id if key_id is not None else env_key_id

	if resolved_secret is None:
		# SK-01: no env var, no arg — refuse to start unless explicit opt-in.
		if os.environ.get("FLOWFORGE_ALLOW_INSECURE_DEFAULT") == "1":
			global _INSECURE_DEFAULT_USED_TOTAL
			_INSECURE_DEFAULT_USED_TOTAL += 1
			_logger.warning(
				"!!! INSECURE DEFAULT IN USE !!! "
				"HmacDevSigning fell back to the hard-coded legacy secret because "
				"FLOWFORGE_ALLOW_INSECURE_DEFAULT=1 is set.  "
				"This path will be removed in the next minor release.  "
				"Set FLOWFORGE_SIGNING_SECRET to a real secret to silence this warning."
			)
			resolved_secret = _LEGACY_DEFAULT_SECRET
			if resolved_key_id is None:
				resolved_key_id = _LEGACY_DEFAULT_KEY_ID
		else:
			raise RuntimeError(
				"HmacDevSigning: explicit secret required; "
				"set FLOWFORGE_SIGNING_SECRET or pass secret= "
				"(or set FLOWFORGE_ALLOW_INSECURE_DEFAULT=1 for the deprecation window)."
			)

	if resolved_key_id is None:
		resolved_key_id = _LEGACY_DEFAULT_KEY_ID

	assert isinstance(resolved_secret, str) and resolved_secret, "resolved secret invariant"
	assert isinstance(resolved_key_id, str) and resolved_key_id, "resolved key_id invariant"

	return {resolved_key_id: resolved_secret}, resolved_key_id


class HmacDevSigning:
	"""HMAC-SHA256 signing adapter for local development.

	Two construction forms:

	1. **Single-key** — ``HmacDevSigning(secret="s", key_id="k")``.
	   Reads ``$FLOWFORGE_SIGNING_SECRET`` / ``$FLOWFORGE_SIGNING_KEY_ID`` if
	   omitted.  Raises ``RuntimeError`` if no secret can be resolved (SK-01).

	2. **Key map** — ``HmacDevSigning(keys={"k1": "s1", "k2": "s2"},
	   current_key_id="k2")``.  Lets the caller carry pre-rotation keys for
	   verifying old signatures while signing with the new one (SK-02).
	"""

	def __init__(
		self,
		secret: str | None = None,
		key_id: str | None = None,
		*,
		keys: dict[str, str] | None = None,
		current_key_id: str | None = None,
	) -> None:
		self._keys, self._current_key_id = _resolve_keys(
			secret=secret,
			key_id=key_id,
			keys=keys,
			current_key_id=current_key_id,
		)

	# ------------------------------------------------------------------
	# SigningPort protocol
	# ------------------------------------------------------------------

	async def sign_payload(self, payload: bytes) -> bytes:
		"""Return a detached HMAC-SHA256 signature for *payload*.

		Always signs with the configured ``current_key_id``.
		"""
		assert isinstance(payload, (bytes, bytearray)), "payload must be bytes"
		secret = self._keys[self._current_key_id]
		return _hmac_sign(secret, self._current_key_id, payload)

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		"""Verify *signature* against *payload* under *key_id*.

		Looks up the secret keyed by *key_id*.  Raises ``UnknownKeyId`` if the
		signer has no record of that key (SK-02).  Otherwise returns
		``True`` / ``False`` for valid / invalid signatures.
		"""
		assert isinstance(payload, (bytes, bytearray)), "payload must be bytes"
		assert isinstance(signature, (bytes, bytearray)), "signature must be bytes"
		assert isinstance(key_id, str) and key_id, "key_id must be a non-empty str"

		try:
			secret = self._keys[key_id]
		except KeyError:
			# Distinct from "wrong signature" so callers can audit precisely.
			raise UnknownKeyId(
				f"HmacDevSigning.verify: unknown key_id={key_id!r}; "
				f"known={sorted(self._keys.keys())!r}"
			) from None

		expected = _hmac_sign(secret, key_id, payload)
		return hmac.compare_digest(expected, signature)

	def current_key_id(self) -> str:
		"""Return the active signing key id."""
		return self._current_key_id

	def known_key_ids(self) -> list[str]:
		"""Return the list of key ids this signer can verify against (SK-02)."""
		return sorted(self._keys.keys())
