"""Manifest signing helpers — sign and verify :class:`JtbdManifest` (E-24).

Uses the ``flowforge.ports.signing.SigningPort`` so the same key
management infrastructure (HMAC, KMS) handles both workflow-elevation
signing and JTBD manifest signing.

Usage::

    from flowforge.testing.port_fakes import InMemorySigning
    from flowforge_jtbd.registry.manifest import JtbdManifest
    from flowforge_jtbd.registry.signing import sign_manifest, verify_manifest

    signer = InMemorySigning()
    manifest = JtbdManifest(name="my-pkg", version="1.0.0")

    signed = await sign_manifest(manifest, signer)
    ok = await verify_manifest(signed, signer)
    assert ok
"""

from __future__ import annotations

import base64
from typing import Any

from .manifest import JtbdManifest


async def sign_manifest(
	manifest: JtbdManifest,
	signer: Any,
) -> JtbdManifest:
	"""Sign *manifest* using *signer* and return a copy with ``signature`` set.

	:param manifest: The manifest to sign (``signature`` must be ``None``).
	:param signer: Any object implementing ``SigningPort`` (has
	  ``sign_payload(bytes) -> bytes`` and ``current_key_id() -> str``).
	:returns: A new :class:`JtbdManifest` with ``signature`` and
	  ``key_id`` populated.
	:raises AssertionError: If *signer* lacks the required methods.
	"""
	sign_fn = getattr(signer, "sign_payload", None)
	key_id_fn = getattr(signer, "current_key_id", None)
	assert callable(sign_fn), "signer must implement sign_payload(bytes) -> bytes"
	assert callable(key_id_fn), "signer must implement current_key_id() -> str"

	payload = manifest.signing_payload()
	sig_bytes: bytes = await sign_fn(payload)
	sig_b64 = base64.b64encode(sig_bytes).decode("ascii")
	key_id: str = key_id_fn()

	return manifest.with_signature(sig_b64, key_id)


async def verify_manifest(
	manifest: JtbdManifest,
	signer: Any,
) -> bool:
	"""Verify the signature on *manifest*.

	:param manifest: A signed manifest (``signature`` and ``key_id`` must
	  be set).
	:param signer: Any object implementing ``SigningPort`` (has
	  ``verify(bytes, bytes, str) -> bool``).
	:returns: ``True`` if the signature is valid; ``False`` otherwise.
	:raises AssertionError: If the manifest is not signed or *signer*
	  lacks the ``verify`` method.
	"""
	assert manifest.signature, "manifest has no signature to verify"
	assert manifest.key_id, "manifest has no key_id to verify against"

	verify_fn = getattr(signer, "verify", None)
	assert callable(verify_fn), "signer must implement verify(bytes, bytes, str) -> bool"

	payload = manifest.signing_payload()
	sig_bytes = base64.b64decode(manifest.signature)
	return bool(await verify_fn(payload, sig_bytes, manifest.key_id))


__all__ = [
	"sign_manifest",
	"verify_manifest",
]
