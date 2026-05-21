"""End-to-end FastAPI tests via httpx ASGITransport.

The transport drives the app in-process — no port bind, no real
network. The same code runs under a uvicorn server in production.
"""

from __future__ import annotations

import base64

import pytest
from flowforge_jtbd.registry.manifest import (
	JtbdManifest,
	bundle_hash,
)
from flowforge_jtbd.registry.signing import sign_manifest
from flowforge_jtbd_hub.app import _AuthHeaderRequest, create_app
from flowforge_jtbd_hub.registry import (
	HubError,
	PackageRegistry,
	TamperedPayloadError,
)
from flowforge_signing_kms import HmacDevSigning
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

AUTH_HEADERS = {"Authorization": "Bearer admin-test-token"}


async def _publish(
	client: AsyncClient,
	signing: HmacDevSigning,
	*,
	name: str = "flowforge-jtbd-insurance",
	version: str = "1.0.0",
	bundle: bytes = b'{"k":"v"}',
	tags: list[str] | None = None,
	description: str = "Insurance domain library",
) -> dict[str, object]:
	manifest = JtbdManifest(
		name=name,
		version=version,
		description=description,
		author="flowforge",
		tags=tags if tags is not None else ["insurance"],
		bundle_hash=bundle_hash(bundle),
	)
	signed = await sign_manifest(manifest, signing)
	response = await client.post(
		"/api/jtbd-hub/packages",
		headers=AUTH_HEADERS,
		json={
			"manifest": signed.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(bundle).decode("ascii"),
			"allow_unsigned": False,
		},
	)
	assert response.status_code == 201, response.text
	return response.json()


async def test_health_endpoint(app_client: AsyncClient) -> None:
	r = await app_client.get("/health")
	assert r.status_code == 200
	assert r.json() == {"status": "ok"}


async def test_auth_header_request_surfaces_case_variants() -> None:
	empty = _AuthHeaderRequest(None)
	assert empty.headers == {}
	with_header = _AuthHeaderRequest("Bearer token")
	assert with_header.headers == {
		"Authorization": "Bearer token",
		"authorization": "Bearer token",
	}


async def test_publish_then_search_finds_package(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	body = await _publish(app_client, signing)
	assert body["name"] == "flowforge-jtbd-insurance"
	assert body["verified"] is False
	assert body["downloads"] == 0

	# Search by query substring.
	r = await app_client.get("/api/jtbd-hub/packages", params={"q": "insurance"})
	assert r.status_code == 200
	results = r.json()
	assert len(results) == 1
	assert results[0]["name"] == "flowforge-jtbd-insurance"


async def test_publish_requires_authentication(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	bundle = b'{"k":"v"}'
	manifest = JtbdManifest(
		name="pkg-auth-required",
		version="1.0.0",
		bundle_hash=bundle_hash(bundle),
	)
	signed = await sign_manifest(manifest, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages",
		json={
			"manifest": signed.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(bundle).decode("ascii"),
		},
	)
	assert r.status_code == 401


async def test_publish_duplicate_version_409(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	manifest = JtbdManifest(
		name="flowforge-jtbd-insurance",
		version="1.0.0",
		bundle_hash=bundle_hash(b'{"k":"v"}'),
	)
	signed = await sign_manifest(manifest, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages",
		headers=AUTH_HEADERS,
		json={
			"manifest": signed.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(b'{"k":"v"}').decode("ascii"),
		},
	)
	assert r.status_code == 409


async def test_package_detail_success_and_missing(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	found = await app_client.get(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0"
	)
	assert found.status_code == 200
	assert found.json()["manifest"]["name"] == "flowforge-jtbd-insurance"

	missing = await app_client.get("/api/jtbd-hub/packages/nope/0.0.0")
	assert missing.status_code == 404


async def test_publish_unsigned_403(app_client: AsyncClient) -> None:
	manifest = JtbdManifest(
		name="pkg-unsigned",
		version="1.0.0",
		bundle_hash=bundle_hash(b'{"k":"v"}'),
	)
	r = await app_client.post(
		"/api/jtbd-hub/packages",
		headers=AUTH_HEADERS,
		json={
			"manifest": manifest.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(b'{"k":"v"}').decode("ascii"),
			"allow_unsigned": False,
		},
	)
	assert r.status_code == 403


async def test_publish_tampered_bundle_400(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	bundle = b'{"k":"v"}'
	manifest = JtbdManifest(
		name="pkg-tamper",
		version="1.0.0",
		bundle_hash=bundle_hash(bundle),
	)
	signed = await sign_manifest(manifest, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages",
		headers=AUTH_HEADERS,
		json={
			"manifest": signed.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(b'{"k":"different"}').decode("ascii"),
		},
	)
	assert r.status_code == 400


async def test_publish_rejects_bad_base64(app_client: AsyncClient) -> None:
	manifest = JtbdManifest(name="pkg-bad-base64", version="1.0.0")
	r = await app_client.post(
		"/api/jtbd-hub/packages",
		headers=AUTH_HEADERS,
		json={
			"manifest": manifest.model_dump(mode="json"),
			"bundle_b64": "not base64!",
			"allow_unsigned": True,
		},
	)
	assert r.status_code == 400
	assert "bundle_b64 is not valid base64" in r.json()["detail"]


async def test_publish_maps_generic_registry_error(
	app_client: AsyncClient,
	registry: PackageRegistry,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def fail_publish(*_args: object, **_kwargs: object) -> object:
		raise HubError("registry closed")

	monkeypatch.setattr(registry, "publish", fail_publish)
	manifest = JtbdManifest(name="pkg-registry-error", version="1.0.0")
	r = await app_client.post(
		"/api/jtbd-hub/packages",
		headers=AUTH_HEADERS,
		json={
			"manifest": manifest.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(b"{}").decode("ascii"),
			"allow_unsigned": True,
		},
	)
	assert r.status_code == 400
	assert r.json()["detail"] == "registry closed"


async def test_install_with_trusted_key(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	bundle = b'{"k":"v"}'
	await _publish(app_client, signing, bundle=bundle)
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/install",
		json={
			"trusted_signing_keys": [
				{"id": signing.current_key_id(), "name": "test"},
			],
		},
	)
	assert r.status_code == 200, r.text
	body = r.json()
	assert base64.b64decode(body["bundle_b64"]) == bundle
	assert body["verified_signature"] is True


async def test_install_untrusted_key_403(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/install",
		json={
			"trusted_signing_keys": [
				{"id": "kms:somebody-else"},
			],
		},
	)
	assert r.status_code == 403


async def test_install_allow_untrusted_query(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/install",
		params={"allow_untrusted": "true"},
		json={"trusted_signing_keys": []},
	)
	assert r.status_code == 200


async def test_install_404_for_unknown_package(
	app_client: AsyncClient,
) -> None:
	r = await app_client.post(
		"/api/jtbd-hub/packages/nope/0.0.0/install",
		json={"trusted_signing_keys": []},
	)
	assert r.status_code == 404


async def test_install_maps_tamper_and_generic_errors(
	app_client: AsyncClient,
	registry: PackageRegistry,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def fail_tamper(*_args: object, **_kwargs: object) -> object:
		raise TamperedPayloadError("stored payload changed")

	monkeypatch.setattr(registry, "install", fail_tamper)
	tampered = await app_client.post(
		"/api/jtbd-hub/packages/pkg/1.0.0/install",
		json={"trusted_signing_keys": []},
	)
	assert tampered.status_code == 409

	async def fail_generic(*_args: object, **_kwargs: object) -> object:
		raise HubError("trust parser failed")

	monkeypatch.setattr(registry, "install", fail_generic)
	generic = await app_client.post(
		"/api/jtbd-hub/packages/pkg/1.0.0/install",
		json={"trusted_signing_keys": []},
	)
	assert generic.status_code == 400
	assert generic.json()["detail"] == "trust parser failed"


async def test_rate_uses_authenticated_principal_not_payload_user(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r1 = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/ratings",
		headers=AUTH_HEADERS,
		json={"user_id": "alice", "stars": 5},
	)
	assert r1.status_code == 201
	assert r1.json()["user_id"] == "legacy_admin"
	r2 = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/ratings",
		headers=AUTH_HEADERS,
		json={"user_id": "bob", "stars": 3},
	)
	assert r2.status_code == 201
	assert r2.json()["user_id"] == "legacy_admin"
	assert r2.json()["average_stars"] == 3.0
	assert r2.json()["rating_count"] == 1


async def test_rate_rejects_invalid_stars(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/ratings",
		headers=AUTH_HEADERS,
		json={"user_id": "alice", "stars": 99},
	)
	assert r.status_code == 422


async def test_rate_requires_authentication(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/ratings",
		json={"user_id": "alice", "stars": 5},
	)
	assert r.status_code == 401


async def test_rate_missing_package_returns_404(app_client: AsyncClient) -> None:
	r = await app_client.post(
		"/api/jtbd-hub/packages/nope/0.0.0/ratings",
		headers=AUTH_HEADERS,
		json={"user_id": "alice", "stars": 5},
	)
	assert r.status_code == 404


async def test_demote_and_verified_missing_package_return_404(
	app_client: AsyncClient,
) -> None:
	demote = await app_client.post(
		"/api/jtbd-hub/packages/nope/0.0.0/demote",
		headers=AUTH_HEADERS,
		json={"reason": "gone"},
	)
	assert demote.status_code == 404

	verified = await app_client.post(
		"/api/jtbd-hub/packages/nope/0.0.0/verified",
		headers=AUTH_HEADERS,
		json={"verified": True},
	)
	assert verified.status_code == 404


async def test_principal_extractor_failure_maps_to_401(
	registry: PackageRegistry,
) -> None:
	def fail_extract(request: object) -> None:
		assert request is not None
		raise ValueError("bad token")

	app = create_app(registry, principal_extractor=fail_extract)
	transport = ASGITransport(app=app)
	async with AsyncClient(transport=transport, base_url="http://hub.test") as client:
		r = await client.post(
			"/api/jtbd-hub/packages/nope/0.0.0/ratings",
			headers={"Authorization": "Bearer invalid"},
			json={"user_id": "alice", "stars": 5},
		)
	assert r.status_code == 401


async def test_demote_requires_admin_token(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	# Without auth header.
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/demote",
		json={"reason": "test"},
	)
	assert r.status_code == 401
	# With correct auth header.
	r2 = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer admin-test-token"},
	)
	assert r2.status_code == 200
	assert r2.json()["demoted"] is True
	assert r2.json()["demote_reason"] == "test"


async def test_demoted_packages_filtered_by_default_search(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer admin-test-token"},
	)
	default = await app_client.get("/api/jtbd-hub/packages")
	assert default.json() == []
	include = await app_client.get(
		"/api/jtbd-hub/packages",
		params={"include_demoted": "true"},
	)
	assert len(include.json()) == 1


async def test_verified_endpoint_flips_badge(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/verified",
		json={"verified": True},
		headers={"Authorization": "Bearer admin-test-token"},
	)
	assert r.status_code == 200
	assert r.json()["verified"] is True


async def test_search_ranks_by_reputation(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	"""More-downloaded package outranks less-downloaded one with same age."""
	bundle_a = b'{"a":1}'
	bundle_b = b'{"b":2}'
	await _publish(
		app_client,
		signing,
		name="pkg-a",
		bundle=bundle_a,
		description="package a",
	)
	await _publish(
		app_client,
		signing,
		name="pkg-b",
		bundle=bundle_b,
		description="package b",
	)
	# Drive a few installs against pkg-b so it has download lead.
	for _ in range(3):
		await app_client.post(
			"/api/jtbd-hub/packages/pkg-b/1.0.0/install",
			params={"allow_untrusted": "true"},
			json={"trusted_signing_keys": []},
		)
	# Add ratings.
	await app_client.post(
		"/api/jtbd-hub/packages/pkg-b/1.0.0/ratings",
		headers=AUTH_HEADERS,
		json={"user_id": "u1", "stars": 5},
	)
	r = await app_client.get("/api/jtbd-hub/packages")
	results = r.json()
	assert [p["name"] for p in results] == ["pkg-b", "pkg-a"]
	# pkg-b is on top — better reputation.
	assert results[0]["reputation"] >= results[1]["reputation"]


async def test_create_app_without_auth_rejects_startup(
	registry: PackageRegistry,
) -> None:
	from flowforge_jtbd_hub.app import create_app

	with pytest.raises(RuntimeError, match="principal_extractor or admin_token"):
		create_app(registry, admin_token=None)


async def test_create_app_explicit_dev_mode_allows_demote(
	registry: PackageRegistry, signing: HmacDevSigning
) -> None:
	"""Authless demote is available only through explicit local dev mode."""
	from flowforge_jtbd_hub.app import create_app
	from httpx import ASGITransport

	app = create_app(registry, admin_token=None, dev_mode=True)
	transport = ASGITransport(app=app)
	async with AsyncClient(transport=transport, base_url="http://h") as client:
		bundle = b'{"k":"v"}'
		await _publish(client, signing, bundle=bundle)
		r = await client.post(
			"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/demote",
			json={"reason": "open dev hub"},
		)
		assert r.status_code == 200
