"""Domain layer for the jtbd-hub registry.

Wraps :class:`flowforge_jtbd.registry.JtbdManifest` (E-24 manifest +
signing primitives shipped earlier) with the publish / install / search
/ rate / demote operations the FastAPI app exposes. In-memory by
default; production hosts swap the storage layer for Postgres + S3 by
inheriting from :class:`PackageRegistry` and overriding the underscore-
prefixed accessors.

Threat model decisions live here:

* Publish refuses an unsigned manifest unless the host explicitly
  passes ``allow_unsigned=True`` (the dev workflow toggles this for
  local hub spinning).
* Install verifies the manifest signature against the caller's
  :class:`TrustConfig`. ``UntrustedSignatureError`` is raised when the
  key id is not in the trusted set; ``allow_untrusted`` opts in.
* Demote NEVER deletes or mutates the package; it flips a status flag
  the search path filters on.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from flowforge_jtbd.registry.manifest import JtbdManifest
from flowforge_jtbd.registry.signing import verify_manifest

from .reputation import DefaultReputationScorer, ReputationScorer, utcnow
from .trust import TrustConfig


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class HubError(Exception):
	"""Base class for jtbd-hub registry errors."""


class PackageNotFoundError(HubError):
	"""Raised when a package@version is not in the registry."""


class PackageAlreadyExistsError(HubError):
	"""Raised on a duplicate publish (immutable per arch §23.8)."""


class UnsignedManifestError(HubError):
	"""Raised when a publish lacks a signature without an allow flag."""


class UntrustedSignatureError(HubError):
	"""Raised when an install would consume a package whose signing
	key is not in the caller's trust set."""


class TamperedPayloadError(HubError):
	"""Raised when the bundle's content hash does not match the
	manifest's recorded ``bundle_hash``."""


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rating:
	"""One user rating against a package version."""

	user_id: str
	stars: int
	created_at: datetime

	def __post_init__(self) -> None:
		if self.stars < 1 or self.stars > 5:
			raise ValueError(
				f"stars must be 1..5; got {self.stars}"
			)


@dataclass
class Package:
	"""Hub-stored package: manifest + tarball + lifecycle state.

	All mutations go through :class:`PackageRegistry` so the hub can
	keep a single audit point for publish / demote / rate events.
	"""

	manifest: JtbdManifest
	bundle: bytes
	published_at: datetime = field(default_factory=utcnow)
	demoted: bool = False
	demote_reason: str | None = None
	verified: bool = False
	downloads: int = 0
	ratings: list[Rating] = field(default_factory=list)

	# ------------------------------------------------------------------
	# convenience
	# ------------------------------------------------------------------

	@property
	def name(self) -> str:
		return self.manifest.name

	@property
	def version(self) -> str:
		return self.manifest.version

	@property
	def domain(self) -> str:
		# JtbdManifest does not carry domain directly; tags are the
		# closest equivalent. Fall back to the first tag if present.
		tags = self.manifest.tags or []
		return tags[0] if tags else ""

	@property
	def average_stars(self) -> float:
		if not self.ratings:
			return 0.0
		return sum(r.stars for r in self.ratings) / len(self.ratings)

	@property
	def rating_count(self) -> int:
		return len(self.ratings)

	# ------------------------------------------------------------------
	# serialisation surface for the API layer
	# ------------------------------------------------------------------

	def to_summary(self) -> dict[str, Any]:
		"""Compact view used by search / list endpoints."""
		return {
			"name": self.name,
			"version": self.version,
			"description": self.manifest.description,
			"author": self.manifest.author,
			"tags": list(self.manifest.tags),
			"published_at": self.published_at.isoformat(),
			"demoted": self.demoted,
			"verified": self.verified,
			"downloads": self.downloads,
			"average_stars": round(self.average_stars, 3),
			"rating_count": self.rating_count,
		}


@dataclass(frozen=True)
class PublishResult:
	package: Package
	scored: float


@dataclass(frozen=True)
class InstallResult:
	manifest: JtbdManifest
	bundle: bytes
	verified_signature: bool
	"""True when the manifest signature verified against the caller's
	trust set. False only when ``allow_untrusted=True`` was passed and
	the signature is unverifiable."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PackageRegistry:
	"""In-memory implementation of the jtbd-hub registry.

	Production hosts subclass + override ``_store_package`` /
	``_load_package`` / ``_iter_packages`` to back with a real DB.
	"""

	def __init__(
		self,
		signing: Any,
		*,
		scorer: ReputationScorer | None = None,
		clock: "Any | None" = None,
	) -> None:
		"""
		:param signing: Any ``SigningPort`` impl (HMAC dev or KMS).
		:param scorer: Optional :class:`ReputationScorer`; the default
		  is the §9.3 ``downloads × stars × age_decay`` policy.
		:param clock: Optional callable returning ``datetime`` (for tests).
		"""
		self._signing = signing
		self._scorer: ReputationScorer = scorer or DefaultReputationScorer()
		self._clock = clock or utcnow
		self._packages: dict[tuple[str, str], Package] = {}
		self._lock = asyncio.Lock()

	# ------------------------------------------------------------------
	# accessors (override in subclasses for non-memory storage)
	# ------------------------------------------------------------------

	def _key(self, name: str, version: str) -> tuple[str, str]:
		return (name, version)

	def _store_package(self, package: Package) -> None:
		self._packages[self._key(package.name, package.version)] = package

	def _load_package(self, name: str, version: str) -> Package | None:
		return self._packages.get(self._key(name, version))

	def _iter_packages(self) -> Iterable[Package]:
		return list(self._packages.values())

	# ------------------------------------------------------------------
	# publish
	# ------------------------------------------------------------------

	async def publish(
		self,
		manifest: JtbdManifest,
		bundle: bytes,
		*,
		allow_unsigned: bool = False,
	) -> PublishResult:
		"""Publish a new package version.

		* Refuses if the manifest lacks a signature unless
		  ``allow_unsigned=True``.
		* Refuses if the bundle's sha256 differs from
		  ``manifest.bundle_hash`` (tamper guard).
		* Refuses if the package@version already exists (immutable).
		* Verifies the manifest signature against the host signing
		  port; a verify failure raises :class:`HubError`.
		"""
		if manifest.signature is None:
			if not allow_unsigned:
				raise UnsignedManifestError(
					"manifest is unsigned; sign it or pass allow_unsigned=True"
				)
		if manifest.bundle_hash is not None:
			expected = "sha256:" + hashlib.sha256(bundle).hexdigest()
			if manifest.bundle_hash != expected:
				raise TamperedPayloadError(
					"manifest.bundle_hash does not match the bundle's sha256;"
					f" expected {manifest.bundle_hash!r} got {expected!r}"
				)

		# Verify the manifest signature with the hub's signing port.
		# When allow_unsigned, we still record the package — useful for
		# local dev — but mark it un-verified.
		signature_ok = False
		if manifest.signature is not None and manifest.key_id is not None:
			signature_ok = await verify_manifest(manifest, self._signing)
			if not signature_ok:
				raise HubError("manifest signature did not verify")

		async with self._lock:
			if self._load_package(manifest.name, manifest.version) is not None:
				raise PackageAlreadyExistsError(
					f"{manifest.name}@{manifest.version} already published"
				)
			package = Package(
				manifest=manifest,
				bundle=bundle,
				published_at=self._clock(),
			)
			self._store_package(package)

		score = self._scorer.score(package, now=self._clock())
		return PublishResult(package=package, scored=score)

	# ------------------------------------------------------------------
	# install
	# ------------------------------------------------------------------

	async def install(
		self,
		name: str,
		version: str,
		*,
		trust: TrustConfig,
		allow_untrusted: bool = False,
	) -> InstallResult:
		"""Resolve + verify + return the bundle for ``name@version``.

		* Looks up the package; raises :class:`PackageNotFoundError`
		  on miss.
		* If the package is demoted, the install still works (consumers
		  can opt in to deprecated packages); the FastAPI layer adds
		  a banner via ``demoted=true`` in the response.
		* Enforces the trust set: signing key must appear in
		  :func:`trust.trusted_key_ids`. ``allow_untrusted=True`` opts
		  out for power users.
		* Re-verifies the manifest signature against the host signing
		  port — defence in depth.
		* Increments the download counter (post-verify so failed
		  attempts don't pollute reputation).
		"""
		package = self._load_package(name, version)
		if package is None:
			raise PackageNotFoundError(f"{name}@{version} not found")

		key_id = package.manifest.key_id
		signature_ok = False
		if package.manifest.signature is not None and key_id is not None:
			signature_ok = await verify_manifest(
				package.manifest, self._signing
			)

		if (not signature_ok or not trust.is_key_trusted(key_id)) and not allow_untrusted:
			raise UntrustedSignatureError(
				f"signing key {key_id!r} for {name}@{version} is not trusted"
				" (pass allow_untrusted=true to override)"
			)

		if trust.verified_publishers_only and not package.verified:
			if not allow_untrusted:
				raise UntrustedSignatureError(
					f"{name}@{version} lacks the verified badge; trust"
					" config requires verified_publishers_only"
				)

		# Tamper guard at install time: bundle bytes must hash to the
		# manifest's bundle_hash. Catches a corrupt store.
		if package.manifest.bundle_hash is not None:
			actual = "sha256:" + hashlib.sha256(package.bundle).hexdigest()
			if actual != package.manifest.bundle_hash:
				raise TamperedPayloadError(
					f"stored bundle for {name}@{version} no longer matches"
					" its manifest's bundle_hash"
				)

		# Mutate counter under lock so concurrent downloads don't race.
		async with self._lock:
			updated = dataclasses.replace(package, downloads=package.downloads + 1)
			self._store_package(updated)

		return InstallResult(
			manifest=updated.manifest,
			bundle=updated.bundle,
			verified_signature=signature_ok,
		)

	# ------------------------------------------------------------------
	# search / metadata
	# ------------------------------------------------------------------

	def get(self, name: str, version: str) -> Package:
		pkg = self._load_package(name, version)
		if pkg is None:
			raise PackageNotFoundError(f"{name}@{version} not found")
		return pkg

	def search(
		self,
		*,
		query: str | None = None,
		domain: str | None = None,
		include_demoted: bool = False,
	) -> list[Package]:
		"""Filter + score-rank packages.

		Match rule: ``query`` is a case-insensitive substring against
		``name | description | tags``. ``domain`` is an exact match
		against the manifest's first tag (we treat tags[0] as the domain
		marker per arch §13.7).
		"""
		q = (query or "").strip().lower()
		results: list[Package] = []
		now = self._clock()
		for pkg in self._iter_packages():
			if pkg.demoted and not include_demoted:
				continue
			if q and not _matches(pkg, q):
				continue
			if domain and pkg.domain != domain:
				continue
			results.append(pkg)
		results.sort(
			key=lambda p: self._scorer.score(p, now=now),
			reverse=True,
		)
		return results

	def reputation(self, package: Package) -> float:
		return self._scorer.score(package, now=self._clock())

	def set_scorer(self, scorer: ReputationScorer) -> None:
		self._scorer = scorer

	# ------------------------------------------------------------------
	# rate
	# ------------------------------------------------------------------

	async def rate(
		self,
		name: str,
		version: str,
		*,
		user_id: str,
		stars: int,
	) -> Rating:
		async with self._lock:
			pkg = self._load_package(name, version)
			if pkg is None:
				raise PackageNotFoundError(f"{name}@{version} not found")
			rating = Rating(
				user_id=user_id, stars=stars, created_at=self._clock()
			)
			# One rating per user — replace if it already exists.
			ratings = [r for r in pkg.ratings if r.user_id != user_id]
			ratings.append(rating)
			updated = dataclasses.replace(pkg, ratings=ratings)
			self._store_package(updated)
		return rating

	# ------------------------------------------------------------------
	# demote / verify
	# ------------------------------------------------------------------

	async def demote(
		self,
		name: str,
		version: str,
		*,
		reason: str,
	) -> Package:
		async with self._lock:
			pkg = self._load_package(name, version)
			if pkg is None:
				raise PackageNotFoundError(f"{name}@{version} not found")
			updated = dataclasses.replace(
				pkg, demoted=True, demote_reason=reason
			)
			self._store_package(updated)
		return updated

	async def mark_verified(
		self,
		name: str,
		version: str,
		*,
		verified: bool = True,
	) -> Package:
		async with self._lock:
			pkg = self._load_package(name, version)
			if pkg is None:
				raise PackageNotFoundError(f"{name}@{version} not found")
			updated = dataclasses.replace(pkg, verified=verified)
			self._store_package(updated)
		return updated


def _matches(package: Package, query: str) -> bool:
	"""Case-insensitive substring match against name / description / tags."""
	if query in package.name.lower():
		return True
	desc = package.manifest.description or ""
	if query in desc.lower():
		return True
	for tag in package.manifest.tags or []:
		if query in tag.lower():
			return True
	return False


def utc_now() -> datetime:
	return datetime.now(timezone.utc)


__all__ = [
	"HubError",
	"InstallResult",
	"Package",
	"PackageAlreadyExistsError",
	"PackageNotFoundError",
	"PackageRegistry",
	"PublishResult",
	"Rating",
	"TamperedPayloadError",
	"UnsignedManifestError",
	"UntrustedSignatureError",
	"utc_now",
]
