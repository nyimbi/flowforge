"""E-73 + E-76 full integration tests — RBAC audit identity and JWT extractor.

Tests:
  E-73 phase 4 — audit events carry principal fields.
  E-73 phase 5 — token rotation / revocation (RevocationList).
  E-73 legacy   — admin_token bridge still yields LEGACY_ADMIN_PRINCIPAL.
  E-76          — full round-trip through JwtPrincipalExtractor.

All tests use:
  - InMemorySigning from flowforge.testing.port_fakes (no external services).
  - In-memory PackageRegistry with an audit_hook closure.
  - No external services required.
"""

from __future__ import annotations

import hashlib
import time

import pytest

from flowforge.testing.port_fakes import InMemorySigning
from flowforge_jtbd.registry.manifest import JtbdManifest
from flowforge_jtbd_hub.jwt_extractor import JwtPrincipalExtractor, make_jwt_extractor
from flowforge_jtbd_hub.rbac import (
	LEGACY_ADMIN_PRINCIPAL,
	Permission,
	Principal,
	Role,
)
from flowforge_jtbd_hub.registry import PackageRegistry
from flowforge_jtbd_hub.token_revocation import RevocationList
from flowforge_jtbd_hub.trust import TrustConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_signing() -> InMemorySigning:
	return InMemorySigning(key_id="test-key")


def _make_manifest(name: str = "test-pkg", version: str = "1.0.0") -> JtbdManifest:
	return JtbdManifest(
		name=name,
		version=version,
		description="E-73 test package",
		author="tester",
		tags=["testing"],
	)


def _bundle() -> bytes:
	return b"fake-bundle-bytes"


def _trust_all() -> TrustConfig:
	"""TrustConfig that accepts everything — no signature enforcement."""
	return TrustConfig(trusted_key_ids=[], verified_publishers_only=False)


class _AuditCapture:
	"""Captures (event_type, payload) tuples from audit_hook calls."""

	def __init__(self) -> None:
		self.events: list[tuple[str, dict]] = []

	def __call__(self, event_type: str, payload: dict) -> None:
		self.events.append((event_type, dict(payload)))

	def events_of(self, event_type: str) -> list[dict]:
		return [p for et, p in self.events if et == event_type]


# ---------------------------------------------------------------------------
# E-73 phase 4: audit events carry principal fields
# ---------------------------------------------------------------------------


async def test_E_73_phase4_audit_carries_principal() -> None:
	"""Publish with a hub_admin principal; audit event must carry principal_* fields."""
	signing = _make_signing()
	audit = _AuditCapture()
	registry = PackageRegistry(signing=signing, audit_hook=audit)

	principal = Principal(
		user_id="alice",
		roles=(Role.HUB_ADMIN,),
		principal_kind="user",
	)

	manifest = _make_manifest()
	await registry.publish(
		manifest,
		_bundle(),
		allow_unsigned=True,
		principal=principal,
	)

	events = audit.events_of("PACKAGE_PUBLISH")
	assert len(events) == 1, f"expected 1 PACKAGE_PUBLISH event, got {len(events)}"
	ev = events[0]
	assert ev["principal_user_id"] == "alice"
	assert ev["principal_kind"] == "user"
	assert "hub_admin" in ev["principal_roles"]


async def test_E_73_phase4_canonical_body_unchanged() -> None:
	"""The canonical audit body (name + version) must survive principal wiring intact.

	E-37 invariant 7: adding principal metadata must not mutate the base event fields.
	"""
	signing = _make_signing()
	audit = _AuditCapture()
	registry = PackageRegistry(signing=signing, audit_hook=audit)

	# Publish without principal first — base payload shape.
	manifest_a = _make_manifest("pkg-a", "1.0.0")
	await registry.publish(manifest_a, _bundle(), allow_unsigned=True, principal=None)

	# Publish with principal — extended payload shape.
	principal = Principal(user_id="bob", roles=(Role.PACKAGE_PUBLISHER,), principal_kind="user")
	manifest_b = _make_manifest("pkg-b", "1.0.0")
	await registry.publish(manifest_b, _bundle(), allow_unsigned=True, principal=principal)

	events = audit.events_of("PACKAGE_PUBLISH")
	assert len(events) == 2

	ev_no_principal = events[0]
	ev_with_principal = events[1]

	# Canonical fields must be present in both.
	assert ev_no_principal["name"] == "pkg-a"
	assert ev_no_principal["version"] == "1.0.0"
	assert ev_with_principal["name"] == "pkg-b"
	assert ev_with_principal["version"] == "1.0.0"

	# Without principal — principal_* fields must be absent.
	assert "principal_user_id" not in ev_no_principal
	assert "principal_kind" not in ev_no_principal
	assert "principal_roles" not in ev_no_principal

	# With principal — canonical fields must not be altered.
	assert ev_with_principal["name"] == "pkg-b"
	assert ev_with_principal["principal_user_id"] == "bob"


async def test_E_73_phase4_demote_carries_principal() -> None:
	"""Demote with a principal; audit event must carry principal_* fields."""
	signing = _make_signing()
	audit = _AuditCapture()
	registry = PackageRegistry(signing=signing, audit_hook=audit)

	manifest = _make_manifest("to-demote", "1.0.0")
	await registry.publish(manifest, _bundle(), allow_unsigned=True)

	principal = Principal(user_id="admin-user", roles=(Role.HUB_ADMIN,), principal_kind="user")
	await registry.demote("to-demote", "1.0.0", reason="bad actor", principal=principal)

	events = audit.events_of("PACKAGE_DEMOTE")
	assert len(events) == 1
	ev = events[0]
	assert ev["principal_user_id"] == "admin-user"
	assert ev["reason"] == "bad actor"


# ---------------------------------------------------------------------------
# E-73 phase 5: token revocation
# ---------------------------------------------------------------------------


async def test_E_73_phase5_token_roundtrip() -> None:
	"""Issue a token, extract it, get back the correct Principal."""
	signing = _make_signing()
	revocation = RevocationList()
	extractor = JwtPrincipalExtractor(signing, revocation=revocation)

	token = await extractor.aissue_token("charlie", ["hub_admin", "auditor"])

	class FakeRequest:
		headers = {"Authorization": f"Bearer {token}"}

	principal = await extractor(FakeRequest())

	assert principal is not None
	assert principal.user_id == "charlie"
	assert Role.HUB_ADMIN in principal.roles
	assert Role.AUDITOR in principal.roles


async def test_E_73_phase5_revoked_token_rejected() -> None:
	"""Issue a token, revoke its jti, verify is_revoked() and extractor both reject it."""
	signing = _make_signing()
	revocation = RevocationList()
	extractor = JwtPrincipalExtractor(signing, revocation=revocation)

	token = await extractor.aissue_token("dave", ["package_publisher"])

	# Parse the jti from the token payload to revoke it.
	import base64
	import json

	payload_b64 = token.split(".")[1]
	padding = 4 - len(payload_b64) % 4
	if padding != 4:
		payload_b64 += "=" * padding
	payload = json.loads(base64.urlsafe_b64decode(payload_b64))
	jti = payload["jti"]

	revocation.revoke("dave", jti, ttl_seconds=30)
	assert revocation.is_revoked("dave", jti)

	class FakeRequest:
		headers = {"Authorization": f"Bearer {token}"}

	principal = await extractor(FakeRequest())
	assert principal is None, "revoked token must return None"


async def test_E_73_phase5_expired_token_rejected() -> None:
	"""Issue a token with exp_seconds=0 (already expired), verify extractor returns None."""
	signing = _make_signing()
	extractor = JwtPrincipalExtractor(signing)

	# exp_seconds=0 → exp = now; by the time verify runs, time.time() > exp.
	token = await extractor.aissue_token("eve", ["package_consumer"], exp_seconds=0)

	# Small sleep is not needed — exp_seconds=0 sets exp=int(time.time())+0,
	# and time.time() is float so by the time the check runs it is already >=exp.
	# If the machine is fast enough that they're equal, nudge by 1 second back.
	import json
	import base64

	payload_b64 = token.split(".")[1]
	padding = 4 - len(payload_b64) % 4
	if padding != 4:
		payload_b64 += "=" * padding
	payload = json.loads(base64.urlsafe_b64decode(payload_b64))
	# Verify our assumption: exp should be <= now already OR we force it by
	# tampering with the token — but that would break the sig.
	# Instead just check: if exp >= time.time(), sleep 1s.
	if payload["exp"] >= time.time():
		import asyncio
		await asyncio.sleep(1.1)

	class FakeRequest:
		headers = {"Authorization": f"Bearer {token}"}

	principal = await extractor(FakeRequest())
	assert principal is None, "expired token must return None"


# ---------------------------------------------------------------------------
# E-73 legacy admin token compat
# ---------------------------------------------------------------------------


async def test_E_73_rbac_legacy_admin_token_compat() -> None:
	"""create_app(admin_token=...) still returns LEGACY_ADMIN_PRINCIPAL for valid token."""
	from httpx import AsyncClient
	from fastapi.testclient import TestClient

	signing = _make_signing()
	registry = PackageRegistry(signing=signing)

	from flowforge_jtbd_hub.app import create_app

	app = create_app(registry, admin_token="test-secret-token")

	# Use synchronous TestClient so no event-loop nesting.
	client = TestClient(app)

	# Publish a package so we have something to demote.
	manifest = _make_manifest("legacy-pkg", "1.0.0")
	import base64

	resp = client.post(
		"/api/jtbd-hub/packages",
		json={
			"manifest": manifest.model_dump(),
			"bundle_b64": base64.b64encode(_bundle()).decode("ascii"),
			"allow_unsigned": True,
		},
		headers={"Authorization": "Bearer test-secret-token"},
	)
	assert resp.status_code == 201, resp.text

	# Demote with the legacy token — must succeed.
	resp = client.post(
		"/api/jtbd-hub/packages/legacy-pkg/1.0.0/demote",
		json={"reason": "legacy-admin-test"},
		headers={"Authorization": "Bearer test-secret-token"},
	)
	assert resp.status_code == 200, resp.text

	# No token → 401.
	resp = client.post(
		"/api/jtbd-hub/packages/legacy-pkg/1.0.0/demote",
		json={"reason": "no-auth"},
	)
	assert resp.status_code == 401, resp.text

	# Wrong token → 401.
	resp = client.post(
		"/api/jtbd-hub/packages/legacy-pkg/1.0.0/demote",
		json={"reason": "bad-token"},
		headers={"Authorization": "Bearer wrong-token"},
	)
	assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# E-76: JWT full round-trip
# ---------------------------------------------------------------------------


async def test_E_76_jwt_roundtrip() -> None:
	"""Full round-trip: issue → extract via make_jwt_extractor factory."""
	signing = _make_signing()
	extractor = make_jwt_extractor(signing)

	token = await extractor.aissue_token("frank", ["hub_admin"])

	class FakeRequest:
		headers = {"Authorization": f"Bearer {token}"}

	principal = await extractor(FakeRequest())

	assert principal is not None
	assert principal.user_id == "frank"
	assert principal.principal_kind == "user"
	assert Role.HUB_ADMIN in principal.roles
	# Verify the Permission gate works.
	assert principal.has(Permission.ADMIN_WRITE)


async def test_E_76_tampered_token_rejected() -> None:
	"""Flipping a bit in the payload segment must cause verification to fail."""
	signing = _make_signing()
	extractor = make_jwt_extractor(signing)

	token = await extractor.aissue_token("grace", ["hub_admin"])

	# Tamper: replace last char of payload segment.
	sig_part, payload_part = token.split(".", 1)
	# Flip the last character.
	tampered_payload = payload_part[:-1] + ("A" if payload_part[-1] != "A" else "B")
	tampered_token = sig_part + "." + tampered_payload

	class FakeRequest:
		headers = {"Authorization": f"Bearer {tampered_token}"}

	principal = await extractor(FakeRequest())
	assert principal is None, "tampered token must return None"


async def test_E_76_missing_bearer_prefix_rejected() -> None:
	"""Authorization header without 'Bearer ' prefix must return None."""
	signing = _make_signing()
	extractor = make_jwt_extractor(signing)

	token = await extractor.aissue_token("heidi", ["auditor"])

	class FakeRequest:
		headers = {"Authorization": token}  # missing "Bearer " prefix

	principal = await extractor(FakeRequest())
	assert principal is None


async def test_E_76_unknown_role_silently_dropped() -> None:
	"""Unknown role strings in the payload must be silently dropped, not raise."""
	import base64
	import json

	signing = _make_signing()
	extractor = make_jwt_extractor(signing)

	# Issue a token with a known + unknown role.
	token = await extractor.aissue_token("ivan", ["hub_admin", "not_a_real_role"])

	class FakeRequest:
		headers = {"Authorization": f"Bearer {token}"}

	principal = await extractor(FakeRequest())
	assert principal is not None
	assert Role.HUB_ADMIN in principal.roles
	# "not_a_real_role" must be absent — silently dropped.
	role_values = [r.value for r in principal.roles]
	assert "not_a_real_role" not in role_values
