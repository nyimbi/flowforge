"""Shared fixtures for the jtbd-hub test suite."""

from __future__ import annotations

import pytest
import pytest_asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from flowforge_jtbd.registry.manifest import (
	JtbdManifest,
	bundle_hash,
)
from flowforge_jtbd.registry.signing import sign_manifest
from flowforge_jtbd_hub.registry import PackageRegistry
from flowforge_signing_kms import HmacDevSigning
from httpx import ASGITransport, AsyncClient

from flowforge_jtbd_hub.app import create_app


@pytest.fixture
def signing() -> HmacDevSigning:
	return HmacDevSigning(secret="hub-test-secret", key_id="hub-test-key")


@pytest.fixture
def registry(signing: HmacDevSigning) -> PackageRegistry:
	# Pin the clock for deterministic reputation tests.
	fixed_clock = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
	return PackageRegistry(signing=signing, clock=lambda: fixed_clock)


@pytest_asyncio.fixture
async def app_client(
	registry: PackageRegistry,
) -> AsyncIterator[AsyncClient]:
	app = create_app(registry, admin_token="admin-test-token")
	transport = ASGITransport(app=app)
	async with AsyncClient(
		transport=transport,
		base_url="http://hub.test",
	) as client:
		yield client


@pytest_asyncio.fixture
async def signed_manifest(
	signing: HmacDevSigning,
) -> JtbdManifest:
	bundle = b'{"project":{"name":"x","package":"x","domain":"insurance"}}'
	manifest = JtbdManifest(
		name="flowforge-jtbd-insurance",
		version="1.0.0",
		description="Insurance domain library",
		author="flowforge",
		tags=["insurance", "claims"],
		bundle_hash=bundle_hash(bundle),
	)
	return await sign_manifest(manifest, signing)


@pytest.fixture
def sample_bundle() -> bytes:
	return b'{"project":{"name":"x","package":"x","domain":"insurance"}}'
