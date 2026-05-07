"""E-37b — Hub trust gate regression tests (JH-01).

Audit finding JH-01 (P0):

* Packages published with ``allow_unsigned=True`` must store an explicit
  ``signed_at_publish=False`` marker on the stored ``Package``.  The
  manifest itself is what the wire carries; the marker pins what the hub
  *saw at publish time* so an install can refuse later.
* Default install path raises :class:`UnsignedPackageRejected` for any
  package whose ``signed_at_publish`` is False.  Explicit
  ``accept_unsigned=True`` install succeeds and emits an audit event
  (``PACKAGE_INSTALL_UNSIGNED``).
* Install error messages must NOT leak internal ``key_id`` values.

Plan reference: framework/docs/audit-fix-plan.md §4.1, §7 (E-37b).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from flowforge_jtbd.registry.manifest import JtbdManifest, bundle_hash
from flowforge_jtbd.registry.signing import sign_manifest
from flowforge_jtbd_hub.registry import (
	PackageRegistry,
	UnsignedPackageRejected,
	UntrustedSignatureError,
)
from flowforge_jtbd_hub.trust import TrustConfig, TrustedKey
from flowforge_signing_kms import HmacDevSigning


def _run(coro):
	loop = asyncio.get_event_loop()
	return loop.run_until_complete(coro)


def _make_signing() -> HmacDevSigning:
	return HmacDevSigning(secret="hub-trust-gate-secret", key_id="hub-trust-gate-key")


def _make_bundle(name: str = "test-pkg") -> bytes:
	return f'{{"project":{{"name":"{name}","package":"{name}","domain":"insurance"}}}}'.encode()


def _make_manifest(name: str = "flowforge-jtbd-insurance", version: str = "1.0.0") -> JtbdManifest:
	bundle = _make_bundle(name)
	return JtbdManifest(
		name=name,
		version=version,
		description="JH-01 hub trust gate fixture",
		author="flowforge",
		tags=["insurance"],
		bundle_hash=bundle_hash(bundle),
	)


def _trust_for(signing: HmacDevSigning) -> TrustConfig:
	return TrustConfig(
		trusted_signing_keys=[TrustedKey(id=signing.current_key_id())],
	)


# ---------------------------------------------------------------------------
# JH-01.a — published unsigned → signed_at_publish=False on stored Package
# ---------------------------------------------------------------------------


def test_JH_01_publish_with_allow_unsigned_marks_signed_at_publish_false():
	"""``Package.signed_at_publish`` must be False after ``publish(..., allow_unsigned=True)``."""
	signing = _make_signing()
	registry = PackageRegistry(signing=signing)
	manifest = _make_manifest()
	bundle = _make_bundle(manifest.name)

	result = _run(
		registry.publish(manifest, bundle, allow_unsigned=True)
	)
	assert result.package.signed_at_publish is False


def test_JH_01_publish_with_signature_marks_signed_at_publish_true():
	"""Signed publish path must set ``signed_at_publish=True``."""
	signing = _make_signing()
	registry = PackageRegistry(signing=signing)
	manifest = _make_manifest()
	bundle = _make_bundle(manifest.name)
	signed = _run(sign_manifest(manifest, signing))

	result = _run(registry.publish(signed, bundle))
	assert result.package.signed_at_publish is True


# ---------------------------------------------------------------------------
# JH-01.b — install of unsigned default-rejects with UnsignedPackageRejected
# ---------------------------------------------------------------------------


def test_JH_01_install_default_rejects_unsigned_package():
	"""Default install of a ``signed_at_publish=False`` package raises ``UnsignedPackageRejected``.

	The error must NOT be a generic ``UntrustedSignatureError`` because we want
	callers to distinguish "we never had a signature" from "signature did not
	land in the trust set".
	"""
	signing = _make_signing()
	registry = PackageRegistry(signing=signing)
	manifest = _make_manifest(name="flowforge-jtbd-insurance", version="2.0.0")
	bundle = _make_bundle(manifest.name)
	_run(registry.publish(manifest, bundle, allow_unsigned=True))

	trust = _trust_for(signing)
	with pytest.raises(UnsignedPackageRejected):
		_run(
			registry.install(
				manifest.name, manifest.version, trust=trust
			)
		)


def test_JH_01_install_with_accept_unsigned_succeeds():
	"""Explicit ``accept_unsigned=True`` install of an unsigned package succeeds."""
	signing = _make_signing()
	registry = PackageRegistry(signing=signing)
	manifest = _make_manifest(name="flowforge-jtbd-insurance", version="2.1.0")
	bundle = _make_bundle(manifest.name)
	_run(registry.publish(manifest, bundle, allow_unsigned=True))

	trust = _trust_for(signing)
	result = _run(
		registry.install(
			manifest.name,
			manifest.version,
			trust=trust,
			accept_unsigned=True,
		)
	)
	assert result.bundle == bundle
	assert result.verified_signature is False


def test_JH_01_install_emits_unsigned_audit_event_on_accept():
	"""``accept_unsigned=True`` path emits ``PACKAGE_INSTALL_UNSIGNED`` to the audit hook."""
	signing = _make_signing()
	captured: list[dict] = []

	def audit_sink(event_type: str, payload: dict) -> None:
		captured.append({"type": event_type, **payload})

	registry = PackageRegistry(signing=signing, audit_hook=audit_sink)
	manifest = _make_manifest(name="flowforge-jtbd-insurance", version="2.2.0")
	bundle = _make_bundle(manifest.name)
	_run(registry.publish(manifest, bundle, allow_unsigned=True))

	trust = _trust_for(signing)
	_run(
		registry.install(
			manifest.name,
			manifest.version,
			trust=trust,
			accept_unsigned=True,
		)
	)

	unsigned_events = [e for e in captured if e["type"] == "PACKAGE_INSTALL_UNSIGNED"]
	assert len(unsigned_events) == 1, captured
	assert unsigned_events[0]["name"] == manifest.name
	assert unsigned_events[0]["version"] == manifest.version


# ---------------------------------------------------------------------------
# JH-01.c — install errors must NOT leak internal key_id
# ---------------------------------------------------------------------------


def test_JH_01_unsigned_rejection_does_not_leak_key_id():
	"""``UnsignedPackageRejected`` message must not contain any ``key_id`` substring."""
	signing = _make_signing()
	registry = PackageRegistry(signing=signing)
	manifest = _make_manifest(name="flowforge-jtbd-insurance", version="3.0.0")
	bundle = _make_bundle(manifest.name)
	_run(registry.publish(manifest, bundle, allow_unsigned=True))

	trust = _trust_for(signing)
	with pytest.raises(UnsignedPackageRejected) as excinfo:
		_run(
			registry.install(
				manifest.name, manifest.version, trust=trust
			)
		)
	msg = str(excinfo.value)
	assert "hub-trust-gate-key" not in msg
	assert "key_id" not in msg.lower()
	# It MAY mention package name@version — that's caller-supplied input,
	# not internal trust-set state.
	assert manifest.name in msg


def test_JH_01_untrusted_signature_does_not_leak_key_id():
	"""``UntrustedSignatureError`` message must not contain the rejected ``key_id``."""
	signing = _make_signing()  # publishes under "hub-trust-gate-key"
	registry = PackageRegistry(signing=signing)
	manifest = _make_manifest(name="flowforge-jtbd-insurance", version="3.1.0")
	bundle = _make_bundle(manifest.name)
	signed = _run(sign_manifest(manifest, signing))
	_run(registry.publish(signed, bundle))

	# Trust set deliberately omits the publishing key.
	other_trust = TrustConfig(
		trusted_signing_keys=[TrustedKey(id="some-other-key")],
	)

	with pytest.raises(UntrustedSignatureError) as excinfo:
		_run(
			registry.install(
				manifest.name, manifest.version, trust=other_trust
			)
		)
	msg = str(excinfo.value)
	assert "hub-trust-gate-key" not in msg
	assert "key_id" not in msg.lower()
	assert manifest.name in msg


# ---------------------------------------------------------------------------
# JH-01.d — accept_unsigned=True does NOT bypass the verified-publishers gate
# ---------------------------------------------------------------------------


def test_JH_01_accept_unsigned_does_not_bypass_verified_publishers_gate():
	"""``accept_unsigned`` opts in to unsigned packages only — not to unverified publishers."""
	signing = _make_signing()
	registry = PackageRegistry(signing=signing)
	manifest = _make_manifest(name="flowforge-jtbd-insurance", version="4.0.0")
	bundle = _make_bundle(manifest.name)
	_run(registry.publish(manifest, bundle, allow_unsigned=True))

	trust_verified_only = TrustConfig(
		trusted_signing_keys=[TrustedKey(id=signing.current_key_id())],
		verified_publishers_only=True,
	)
	with pytest.raises(UntrustedSignatureError):
		_run(
			registry.install(
				manifest.name,
				manifest.version,
				trust=trust_verified_only,
				accept_unsigned=True,
			)
		)
