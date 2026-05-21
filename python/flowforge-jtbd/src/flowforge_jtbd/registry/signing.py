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
    if not ok:
        raise RuntimeError("manifest signature verification failed")
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, cast

from flowforge.ports.signing import SigningPort

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
    :raises TypeError: If *signer* lacks the required methods.
    """
    sign_fn = getattr(signer, "sign_payload", None)
    key_id_fn = getattr(signer, "current_key_id", None)
    if not callable(sign_fn):
        raise TypeError("signer must implement sign_payload(bytes) -> bytes")
    if not callable(key_id_fn):
        raise TypeError("signer must implement current_key_id() -> str")
    signer_port = cast(SigningPort, signer)

    payload = manifest.signing_payload()
    sig_bytes = await signer_port.sign_payload(payload)
    sig_b64 = base64.b64encode(sig_bytes).decode("ascii")
    key_id = signer_port.current_key_id()

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
    :raises ValueError: If the manifest is not signed.
    :raises TypeError: If *signer*
      lacks the ``verify`` method.
    """
    if not manifest.signature:
        raise ValueError("manifest has no signature to verify")
    if not manifest.key_id:
        raise ValueError("manifest has no key_id to verify against")

    verify_fn = getattr(signer, "verify", None)
    if not callable(verify_fn):
        raise TypeError("signer must implement verify(bytes, bytes, str) -> bool")
    signer_port = cast(SigningPort, signer)

    payload = manifest.signing_payload()
    try:
        sig_bytes = base64.b64decode(manifest.signature, validate=True)
    except (binascii.Error, ValueError):
        return False
    return bool(await signer_port.verify(payload, sig_bytes, manifest.key_id))


__all__ = [
    "sign_manifest",
    "verify_manifest",
]
