"""E-73 jtbd-hub RBAC acceptance tests.

Covers the four phases that landed in this delivery:
  1. Principal + Role + Permission types (rbac.py)
  2. PrincipalExtractor protocol + dependency wiring (app.py)
  3. Per-route authorisation gate (require_permission)
  4. Backward-compat with E-58 admin_token= legacy bridge

Phase 5 (token rotation + revocation via flowforge-signing-kms) and
phase 6 (full per-user audit identity in registry events) are tracked
as follow-ups in framework/docs/design/E-73-jtbd-hub-rbac.md.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from flowforge_jtbd.registry.manifest import JtbdManifest, bundle_hash
from flowforge_jtbd.registry.signing import sign_manifest
from flowforge_signing_kms import HmacDevSigning
from flowforge_jtbd_hub import (
	LEGACY_ADMIN_PRINCIPAL,
	Permission,
	Principal,
	PrincipalExtractor,
	Role,
	create_app,
	role_permissions,
)
from flowforge_jtbd_hub.registry import PackageRegistry


def _run(coro):
	return asyncio.run(coro)


def _make_signing() -> HmacDevSigning:
	return HmacDevSigning(secret="rbac-test-secret", key_id="rbac-test-key")


def _make_bundle(name: str = "rbac-test-pkg") -> bytes:
	return f'{{"project":{{"name":"{name}","package":"{name}","domain":"insurance"}}}}'.encode()


def _make_manifest(name: str = "flowforge-jtbd-rbac-test", version: str = "1.0.0") -> JtbdManifest:
	bundle = _make_bundle(name)
	return JtbdManifest(
		name=name,
		version=version,
		description="E-73 RBAC fixture",
		author="flowforge",
		tags=["rbac"],
		bundle_hash=bundle_hash(bundle),
	)


def _publish(registry: PackageRegistry, *, signed: bool = True) -> tuple[str, str]:
	"""Publish a fixture package; return (name, version)."""
	signing = _make_signing()
	manifest = _make_manifest()
	bundle = _make_bundle(manifest.name)
	if signed:
		signed_manifest = _run(sign_manifest(manifest, signing))
		_run(registry.publish(signed_manifest, bundle))
	else:
		_run(registry.publish(manifest, bundle, allow_unsigned=True))
	return manifest.name, manifest.version


# ---------------------------------------------------------------------------
# Phase 1: Principal / Role / Permission types
# ---------------------------------------------------------------------------


def test_E_73_role_has_permission():
	"""Role -> permissions mapping covers each declared role."""
	hub_admin_perms = role_permissions(Role.HUB_ADMIN)
	assert Permission.PACKAGE_PUBLISH in hub_admin_perms
	assert Permission.ADMIN_WRITE in hub_admin_perms
	assert Permission.AUDIT_READ in hub_admin_perms

	publisher_perms = role_permissions(Role.PACKAGE_PUBLISHER)
	assert Permission.PACKAGE_PUBLISH in publisher_perms
	assert Permission.ADMIN_WRITE not in publisher_perms

	consumer_perms = role_permissions(Role.PACKAGE_CONSUMER)
	assert Permission.PACKAGE_INSTALL in consumer_perms
	assert Permission.PACKAGE_PUBLISH not in consumer_perms


def test_E_73_principal_has_permission():
	"""Principal.has() walks the role union."""
	p = Principal(
		user_id="alice",
		roles=(Role.PACKAGE_PUBLISHER, Role.AUDITOR),
	)
	assert p.has(Permission.PACKAGE_PUBLISH)
	assert p.has(Permission.AUDIT_READ)
	assert p.has(Permission.ADMIN_READ)
	assert not p.has(Permission.ADMIN_WRITE)


def test_E_73_legacy_admin_principal_has_admin_write():
	"""The legacy bridge maps to a Principal that satisfies ADMIN_WRITE."""
	assert LEGACY_ADMIN_PRINCIPAL.has(Permission.ADMIN_WRITE)
	assert LEGACY_ADMIN_PRINCIPAL.principal_kind == "legacy_admin"


def test_E_73_principal_kind_default_is_user():
	"""Per-user principals (default kind) distinguish from legacy bridge."""
	p = Principal(user_id="alice", roles=(Role.HUB_ADMIN,))
	assert p.principal_kind == "user"


# ---------------------------------------------------------------------------
# Phase 2 + 3: PrincipalExtractor + per-route authorisation
# ---------------------------------------------------------------------------


def _extractor_alice_admin(req: Any) -> Principal | None:
	auth = req.headers.get("Authorization") if req else None
	if auth == "Bearer alice-token":
		return Principal(user_id="alice", roles=(Role.HUB_ADMIN,))
	return None


def _extractor_bob_auditor(req: Any) -> Principal | None:
	auth = req.headers.get("Authorization") if req else None
	if auth == "Bearer bob-token":
		return Principal(user_id="bob", roles=(Role.AUDITOR,))
	return None


def test_E_73_extractor_grants_admin_write():
	"""Authenticated principal with ADMIN_WRITE -> 200 on demote."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, principal_extractor=_extractor_alice_admin)
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer alice-token"},
	)
	assert resp.status_code == 200, resp.text


def test_E_73_extractor_missing_credentials_returns_401():
	"""No Authorization header -> 401 when extractor is set."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, principal_extractor=_extractor_alice_admin)
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "test"},
	)
	assert resp.status_code == 401


def test_E_73_extractor_wrong_role_returns_403():
	"""Authenticated principal without ADMIN_WRITE -> 403, not 401."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, principal_extractor=_extractor_bob_auditor)
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer bob-token"},
	)
	assert resp.status_code == 403, resp.text
	assert "admin.write" in resp.text


def test_E_73_extractor_invalid_token_returns_401():
	"""Header present but not recognised by extractor -> 401."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, principal_extractor=_extractor_alice_admin)
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer unknown-token"},
	)
	assert resp.status_code == 401


def test_E_73_set_verified_also_gated():
	"""verified-badge route uses the same ADMIN_WRITE gate."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, principal_extractor=_extractor_alice_admin)
	client = TestClient(app)

	# 200 with auth.
	resp_ok = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/verified",
		json={"verified": True},
		headers={"Authorization": "Bearer alice-token"},
	)
	assert resp_ok.status_code == 200, resp_ok.text

	# 401 without auth.
	resp_unauth = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/verified",
		json={"verified": True},
	)
	assert resp_unauth.status_code == 401


# ---------------------------------------------------------------------------
# Phase 4 backward-compat: E-58 admin_token= legacy bridge
# ---------------------------------------------------------------------------


def test_E_73_legacy_admin_token_still_works():
	"""admin_token=... maps valid bearer -> LEGACY_ADMIN_PRINCIPAL ->
	ADMIN_WRITE granted -> 200 on demote."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, admin_token="legacy-shared-secret")
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer legacy-shared-secret"},
	)
	assert resp.status_code == 200, resp.text


def test_E_73_legacy_admin_token_rotation_list():
	"""Comma-separated rotation list (E-58 JH-04): each entry grants admin."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, admin_token="old-token, new-token")
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "rotation pre-cutover"},
		headers={"Authorization": "Bearer old-token"},
	)
	assert resp.status_code == 200

	# Re-publish so we can demote a fresh package.
	registry2 = PackageRegistry(signing=_make_signing())
	name2, version2 = _publish(registry2)
	app2 = create_app(registry2, admin_token="old-token, new-token")
	client2 = TestClient(app2)
	resp2 = client2.post(
		f"/api/jtbd-hub/packages/{name2}/{version2}/demote",
		json={"reason": "rotation post-cutover"},
		headers={"Authorization": "Bearer new-token"},
	)
	assert resp2.status_code == 200


def test_E_73_legacy_admin_token_invalid_returns_401():
	"""Invalid legacy token -> 401."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry, admin_token="legacy-shared-secret")
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer wrong-token"},
	)
	assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Hybrid: extractor + admin_token both configured (staged migration)
# ---------------------------------------------------------------------------


def test_E_73_hybrid_extractor_and_legacy_token_both_accept():
	"""When both are configured, EITHER credential works."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(
		registry,
		principal_extractor=_extractor_alice_admin,
		admin_token="legacy-token",
	)
	client = TestClient(app)

	# Per-user route works.
	resp_user = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "user"},
		headers={"Authorization": "Bearer alice-token"},
	)
	assert resp_user.status_code == 200

	# Re-publish then exercise the legacy route.
	registry2 = PackageRegistry(signing=_make_signing())
	name2, version2 = _publish(registry2)
	app2 = create_app(
		registry2,
		principal_extractor=_extractor_alice_admin,
		admin_token="legacy-token",
	)
	client2 = TestClient(app2)
	resp_legacy = client2.post(
		f"/api/jtbd-hub/packages/{name2}/{version2}/demote",
		json={"reason": "legacy"},
		headers={"Authorization": "Bearer legacy-token"},
	)
	assert resp_legacy.status_code == 200


# ---------------------------------------------------------------------------
# Dev mode (no auth configured)
# ---------------------------------------------------------------------------


def test_E_73_dev_mode_open_admin():
	"""When neither extractor nor admin_token is set, admin endpoints
	stay open (current dev-mode behaviour preserved)."""
	registry = PackageRegistry(signing=_make_signing())
	name, version = _publish(registry)

	app = create_app(registry)
	client = TestClient(app)

	resp = client.post(
		f"/api/jtbd-hub/packages/{name}/{version}/demote",
		json={"reason": "dev mode"},
	)
	assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PrincipalExtractor protocol shape
# ---------------------------------------------------------------------------


def test_E_73_principal_extractor_protocol_runtime_check():
	"""Custom extractors that implement ``__call__`` are accepted."""

	class JwtExtractor:
		def __call__(self, request: Any) -> Principal | None:
			# A real impl would verify a JWT via flowforge-signing-kms.
			return None

	extractor: PrincipalExtractor = JwtExtractor()
	assert callable(extractor)
