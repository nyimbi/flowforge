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
from flowforge_jtbd_hub.registry import PackageRegistry
from flowforge_signing_kms import HmacDevSigning
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


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
		json={
			"manifest": signed.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(b'{"k":"v"}').decode("ascii"),
		},
	)
	assert r.status_code == 409


async def test_publish_unsigned_403(app_client: AsyncClient) -> None:
	manifest = JtbdManifest(
		name="pkg-unsigned",
		version="1.0.0",
		bundle_hash=bundle_hash(b'{"k":"v"}'),
	)
	r = await app_client.post(
		"/api/jtbd-hub/packages",
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
		json={
			"manifest": signed.model_dump(mode="json"),
			"bundle_b64": base64.b64encode(b'{"k":"different"}').decode("ascii"),
		},
	)
	assert r.status_code == 400


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


async def test_rate_returns_average(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r1 = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/ratings",
		json={"user_id": "alice", "stars": 5},
	)
	assert r1.status_code == 201
	r2 = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/ratings",
		json={"user_id": "bob", "stars": 3},
	)
	assert r2.status_code == 201
	assert r2.json()["average_stars"] == 4.0
	assert r2.json()["rating_count"] == 2


async def test_rate_rejects_invalid_stars(
	app_client: AsyncClient, signing: HmacDevSigning
) -> None:
	await _publish(app_client, signing)
	r = await app_client.post(
		"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/ratings",
		json={"user_id": "alice", "stars": 99},
	)
	assert r.status_code == 422


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
		json={"user_id": "u1", "stars": 5},
	)
	r = await app_client.get("/api/jtbd-hub/packages")
	results = r.json()
	assert [p["name"] for p in results] == ["pkg-b", "pkg-a"]
	# pkg-b is on top — better reputation.
	assert results[0]["reputation"] >= results[1]["reputation"]


async def test_create_app_without_admin_token_allows_demote(
	registry: PackageRegistry, signing: HmacDevSigning
) -> None:
	"""When admin_token=None the demote endpoint is unguarded — useful
	for local dev hub spinning."""
	from flowforge_jtbd_hub.app import create_app
	from httpx import ASGITransport

	app = create_app(registry, admin_token=None)
	transport = ASGITransport(app=app)
	async with AsyncClient(transport=transport, base_url="http://h") as client:
		bundle = b'{"k":"v"}'
		await _publish(client, signing, bundle=bundle)
		r = await client.post(
			"/api/jtbd-hub/packages/flowforge-jtbd-insurance/1.0.0/demote",
			json={"reason": "open dev hub"},
		)
		assert r.status_code == 200
