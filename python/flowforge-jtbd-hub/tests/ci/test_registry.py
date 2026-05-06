"""Domain-layer tests for the jtbd-hub registry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from flowforge_jtbd.registry.manifest import (
	JtbdManifest,
	bundle_hash,
)
from flowforge_jtbd.registry.signing import sign_manifest
from flowforge_jtbd_hub.registry import (
	HubError,
	PackageAlreadyExistsError,
	PackageNotFoundError,
	PackageRegistry,
	TamperedPayloadError,
	UnsignedManifestError,
	UntrustedSignatureError,
)
from flowforge_jtbd_hub.reputation import DefaultReputationScorer
from flowforge_jtbd_hub.trust import TrustConfig, TrustedKey
from flowforge_signing_kms import HmacDevSigning

pytestmark = pytest.mark.asyncio


def _make_manifest(
	*,
	name: str = "flowforge-jtbd-insurance",
	version: str = "1.0.0",
	bundle: bytes = b'{"k":"v"}',
	tags: list[str] | None = None,
) -> JtbdManifest:
	return JtbdManifest(
		name=name,
		version=version,
		description=f"{name} description",
		author="flowforge",
		tags=tags if tags is not None else ["insurance"],
		bundle_hash=bundle_hash(bundle),
	)


async def test_publish_and_resolve_round_trip(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	result = await registry.publish(manifest, sample_bundle)
	assert result.package.name == "flowforge-jtbd-insurance"
	assert result.package.version == "1.0.0"
	assert registry.get("flowforge-jtbd-insurance", "1.0.0").bundle == sample_bundle


async def test_publish_refuses_unsigned_without_flag(
	registry: PackageRegistry, sample_bundle: bytes
) -> None:
	manifest = _make_manifest(bundle=sample_bundle)
	with pytest.raises(UnsignedManifestError):
		await registry.publish(manifest, sample_bundle)


async def test_publish_allows_unsigned_with_flag(
	registry: PackageRegistry, sample_bundle: bytes
) -> None:
	manifest = _make_manifest(bundle=sample_bundle)
	result = await registry.publish(
		manifest, sample_bundle, allow_unsigned=True
	)
	assert result.package.manifest.signature is None


async def test_publish_detects_tampered_bundle(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	with pytest.raises(TamperedPayloadError):
		await registry.publish(manifest, sample_bundle + b"-tampered")


async def test_publish_rejects_duplicate_version(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	# Re-sign because manifest.signature already populated would also fail.
	manifest2 = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	with pytest.raises(PackageAlreadyExistsError):
		await registry.publish(manifest2, sample_bundle)


async def test_publish_rejects_invalid_signature(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	# Tamper the signed manifest after signing.
	tampered = manifest.model_copy(update={"description": "altered"})
	with pytest.raises(HubError):
		await registry.publish(tampered, sample_bundle)


async def test_install_with_trusted_key_succeeds(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	trust = TrustConfig(
		trusted_signing_keys=[TrustedKey(id=signing.current_key_id())],
	)
	result = await registry.install(
		"flowforge-jtbd-insurance", "1.0.0", trust=trust
	)
	assert result.bundle == sample_bundle
	assert result.verified_signature is True
	# Download counter ticked.
	assert registry.get("flowforge-jtbd-insurance", "1.0.0").downloads == 1


async def test_install_untrusted_key_raises(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	trust = TrustConfig(trusted_signing_keys=[TrustedKey(id="kms:other-key")])
	with pytest.raises(UntrustedSignatureError):
		await registry.install(
			"flowforge-jtbd-insurance", "1.0.0", trust=trust
		)


async def test_install_allow_untrusted_overrides(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	trust = TrustConfig()
	result = await registry.install(
		"flowforge-jtbd-insurance",
		"1.0.0",
		trust=trust,
		allow_untrusted=True,
	)
	assert result.bundle == sample_bundle


async def test_install_verified_publishers_only_blocks_unverified(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	trust = TrustConfig(
		trusted_signing_keys=[TrustedKey(id=signing.current_key_id())],
		verified_publishers_only=True,
	)
	with pytest.raises(UntrustedSignatureError):
		await registry.install(
			"flowforge-jtbd-insurance", "1.0.0", trust=trust
		)
	# After marking as verified, install succeeds.
	await registry.mark_verified("flowforge-jtbd-insurance", "1.0.0")
	result = await registry.install(
		"flowforge-jtbd-insurance", "1.0.0", trust=trust
	)
	assert result.verified_signature is True


async def test_install_missing_package_raises(
	registry: PackageRegistry,
) -> None:
	with pytest.raises(PackageNotFoundError):
		await registry.install("nope", "0.0.0", trust=TrustConfig())


async def test_search_filters_demoted_by_default(
	registry: PackageRegistry, signing: HmacDevSigning
) -> None:
	bundle_a = b'{"a":1}'
	bundle_b = b'{"b":2}'
	a = await sign_manifest(
		_make_manifest(name="pkg-a", bundle=bundle_a, tags=["insurance"]),
		signing,
	)
	b = await sign_manifest(
		_make_manifest(name="pkg-b", bundle=bundle_b, tags=["banking"]),
		signing,
	)
	await registry.publish(a, bundle_a)
	await registry.publish(b, bundle_b)
	await registry.demote("pkg-a", "1.0.0", reason="security advisory")

	default_search = registry.search()
	assert {p.name for p in default_search} == {"pkg-b"}

	include_demoted = registry.search(include_demoted=True)
	assert {p.name for p in include_demoted} == {"pkg-a", "pkg-b"}


async def test_search_query_and_domain(
	registry: PackageRegistry, signing: HmacDevSigning
) -> None:
	bundle_a = b'{"a":1}'
	bundle_b = b'{"b":2}'
	a = await sign_manifest(
		_make_manifest(name="pkg-claims", bundle=bundle_a, tags=["insurance"]),
		signing,
	)
	b = await sign_manifest(
		_make_manifest(name="pkg-loans", bundle=bundle_b, tags=["banking"]),
		signing,
	)
	await registry.publish(a, bundle_a)
	await registry.publish(b, bundle_b)

	by_query = registry.search(query="loan")
	assert {p.name for p in by_query} == {"pkg-loans"}

	by_domain = registry.search(domain="insurance")
	assert {p.name for p in by_domain} == {"pkg-claims"}


async def test_rate_replaces_user_rating(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	await registry.rate(
		"flowforge-jtbd-insurance", "1.0.0", user_id="alice", stars=4
	)
	# Same user re-rates — count stays at 1, average flips to 5.
	await registry.rate(
		"flowforge-jtbd-insurance", "1.0.0", user_id="alice", stars=5
	)
	pkg = registry.get("flowforge-jtbd-insurance", "1.0.0")
	assert pkg.rating_count == 1
	assert pkg.average_stars == 5.0


async def test_rate_rejects_out_of_range_stars(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	with pytest.raises(ValueError):
		await registry.rate(
			"flowforge-jtbd-insurance", "1.0.0", user_id="alice", stars=0
		)
	with pytest.raises(ValueError):
		await registry.rate(
			"flowforge-jtbd-insurance", "1.0.0", user_id="alice", stars=6
		)


async def test_demote_does_not_delete_or_mutate_manifest(
	registry: PackageRegistry, signing: HmacDevSigning, sample_bundle: bytes
) -> None:
	manifest = await sign_manifest(_make_manifest(bundle=sample_bundle), signing)
	await registry.publish(manifest, sample_bundle)
	pkg_before = registry.get("flowforge-jtbd-insurance", "1.0.0")
	await registry.demote(
		"flowforge-jtbd-insurance", "1.0.0", reason="CVE-2026-9001"
	)
	pkg_after = registry.get("flowforge-jtbd-insurance", "1.0.0")
	assert pkg_after.demoted is True
	assert pkg_after.demote_reason == "CVE-2026-9001"
	# Manifest immutable — same signature, same bundle hash, same fields.
	assert pkg_after.manifest == pkg_before.manifest


async def test_reputation_decays_with_age() -> None:
	"""Older packages with the same downloads + stars rank below newer ones."""
	scorer = DefaultReputationScorer(half_life_days=180.0)
	now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)

	class _P:
		def __init__(self, age_days: int) -> None:
			self.downloads = 100
			self.average_stars = 4.5
			self.rating_count = 5
			self.published_at = now - timedelta(days=age_days)
			self.demoted = False

	new = scorer.score(_P(age_days=0), now=now)
	old = scorer.score(_P(age_days=365), now=now)
	assert new > old
	demoted = _P(age_days=0)
	demoted.demoted = True
	assert scorer.score(demoted, now=now) < new
