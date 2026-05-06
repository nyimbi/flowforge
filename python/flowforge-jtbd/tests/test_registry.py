"""Tests for E-24 jtbd-hub registry: manifest + signing."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from typing import Any

from flowforge_jtbd.registry.manifest import (
	JtbdManifest,
	bundle_hash,
	manifest_from_bundle,
)
from flowforge_jtbd.registry.signing import sign_manifest, verify_manifest


def _run(coro: Any) -> Any:
	return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fake signer matching SigningPort protocol
# ---------------------------------------------------------------------------


class _FakeSigner:
	"""Minimal SigningPort stub for testing."""

	_KEY_ID = "test-hmac-v1"
	_SECRET = b"test-secret"

	def current_key_id(self) -> str:
		return self._KEY_ID

	async def sign_payload(self, payload: bytes) -> bytes:
		import hmac
		return hmac.new(self._SECRET, payload, hashlib.sha256).digest()

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		import hmac
		expected = hmac.new(self._SECRET, payload, hashlib.sha256).digest()
		return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# JtbdManifest
# ---------------------------------------------------------------------------


def test_manifest_default_schema_version() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	assert m.schema_version == "1"


def test_manifest_signing_payload_excludes_signature() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0", signature="xxx", key_id="k")
	payload = m.signing_payload()
	data = json.loads(payload)
	assert "signature" not in data
	assert "key_id" not in data


def test_manifest_signing_payload_includes_name_version() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	data = json.loads(m.signing_payload())
	assert data["name"] == "my-pkg"
	assert data["version"] == "1.0.0"


def test_manifest_with_signature() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	signed = m.with_signature("sig123", "key-1")
	assert signed.signature == "sig123"
	assert signed.key_id == "key-1"
	# Original unchanged
	assert m.signature is None


def test_manifest_with_timestamp() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	ts = m.with_timestamp()
	assert ts.published_at is not None


def test_manifest_tags() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0", tags=["insurance", "claims"])
	assert "insurance" in m.tags


# ---------------------------------------------------------------------------
# bundle_hash
# ---------------------------------------------------------------------------


def test_bundle_hash_format() -> None:
	h = bundle_hash(b"hello")
	assert h.startswith("sha256:")
	assert len(h) == 7 + 64  # "sha256:" + 64 hex chars


def test_bundle_hash_deterministic() -> None:
	data = b"my bundle data"
	assert bundle_hash(data) == bundle_hash(data)


def test_bundle_hash_differs_on_different_input() -> None:
	assert bundle_hash(b"a") != bundle_hash(b"b")


# ---------------------------------------------------------------------------
# manifest_from_bundle
# ---------------------------------------------------------------------------


def _sample_bundle_bytes() -> bytes:
	bundle = {
		"project": {"name": "test", "package": "test", "domain": "test"},
		"shared": {"roles": ["user"], "permissions": ["test.read"]},
		"jtbds": [{
			"id": "claim_intake",
			"actor": {"role": "user"},
			"situation": "s", "motivation": "m", "outcome": "o",
			"success_criteria": ["ok"],
		}],
	}
	return json.dumps(bundle, sort_keys=True).encode("utf-8")


def test_manifest_from_bundle_sets_hashes() -> None:
	raw = _sample_bundle_bytes()
	m = manifest_from_bundle("test-pkg", "1.0.0", raw)
	assert m.bundle_hash is not None
	assert m.bundle_hash.startswith("sha256:")
	assert m.spec_hash is not None
	assert m.spec_hash.startswith("sha256:")


def test_manifest_from_bundle_name_version() -> None:
	m = manifest_from_bundle("test-pkg", "2.1.0", b"{}")
	assert m.name == "test-pkg"
	assert m.version == "2.1.0"


def test_manifest_from_bundle_optional_fields() -> None:
	m = manifest_from_bundle(
		"test-pkg", "1.0.0", b"{}",
		description="Test package",
		author="test@example.com",
		tags=["test"],
	)
	assert m.description == "Test package"
	assert m.author == "test@example.com"
	assert "test" in m.tags


# ---------------------------------------------------------------------------
# sign_manifest + verify_manifest
# ---------------------------------------------------------------------------


def test_sign_manifest_adds_signature() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	signer = _FakeSigner()
	signed = _run(sign_manifest(m, signer))
	assert signed.signature is not None
	assert signed.key_id == "test-hmac-v1"


def test_sign_manifest_signature_is_base64() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	signed = _run(sign_manifest(m, _FakeSigner()))
	# Should decode without error
	raw = base64.b64decode(signed.signature)
	assert len(raw) == 32  # SHA-256 HMAC = 32 bytes


def test_verify_manifest_valid_signature() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	signer = _FakeSigner()
	signed = _run(sign_manifest(m, signer))
	assert _run(verify_manifest(signed, signer)) is True


def test_verify_manifest_tampered_fails() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0")
	signer = _FakeSigner()
	signed = _run(sign_manifest(m, signer))
	# Tamper: change the name after signing
	tampered = signed.model_copy(update={"name": "evil-pkg"})
	assert _run(verify_manifest(tampered, signer)) is False


def test_verify_manifest_wrong_signature_fails() -> None:
	m = JtbdManifest(name="my-pkg", version="1.0.0", signature="AAAA", key_id="k")
	signer = _FakeSigner()
	assert _run(verify_manifest(m, signer)) is False


def test_sign_round_trip_with_bundle_metadata() -> None:
	raw = _sample_bundle_bytes()
	m = manifest_from_bundle("insurance-demo", "1.0.0", raw, author="dev@example.com")
	signer = _FakeSigner()
	signed = _run(sign_manifest(m.with_timestamp(), signer))
	assert _run(verify_manifest(signed, signer)) is True
