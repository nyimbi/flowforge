"""E-58 — jtbd-hub residual hardening.

Audit-fix-plan §4.2 / §4.3 / §4.4 JH-02..JH-06, §7 E-58:

- JH-02 (P1): per-replica download counter must converge in a shared DB —
  in-memory mutation is replaced with a ``_increment_downloads`` hook
  subclasses override for an atomic UPDATE.
- JH-03 (P1): ``verified_at_install`` cached on the Package; subsequent
  installs within the cache window skip the signature reverify.
- JH-04 (P2 split): admin token supports rotation — env-var with
  comma-separated list (any token in the list authenticates); admin
  actions emit an audit event so an operator can attribute the call.
- JH-05 (P2): trust-file paths resolve via :mod:`platformdirs` so
  Windows hosts pick up the right directory.
- JH-06 (P2): ``_load_yaml_trust`` / ``_load_pyproject_trust`` catch
  exactly :class:`pydantic.ValidationError` — OOM, KeyboardInterrupt,
  unrelated bugs propagate.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


def _drive(coro: Any) -> Any:
	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		return loop.run_until_complete(coro)
	finally:
		loop.close()


def _signing_port() -> Any:
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	return HmacDevSigning(secret="test-secret", key_id="test-key")


def _publish_signed(registry: Any, name: str = "acme.demo", version: str = "1.0.0") -> Any:
	from flowforge_jtbd.registry.manifest import JtbdManifest
	from flowforge_jtbd.registry.signing import sign_manifest

	bundle = b'{"jtbds":[]}'
	manifest = JtbdManifest(
		name=name,
		version=version,
		description="d",
		author="a",
		bundle_hash="sha256:" + hashlib.sha256(bundle).hexdigest(),
	)
	signed = _drive(sign_manifest(manifest, registry._signing))
	_drive(registry.publish(signed, bundle))
	return signed


# ---------------------------------------------------------------------------
# JH-02 — download counter is hookable
# ---------------------------------------------------------------------------


def test_JH_02_increment_downloads_hook_called_per_install() -> None:
	"""Each install dispatches through ``_increment_downloads`` exactly
	once. Subclasses override that hook to UPDATE a DB row atomically."""

	from flowforge_jtbd_hub.registry import PackageRegistry
	from flowforge_jtbd_hub.trust import TrustConfig

	calls: list[tuple[str, str]] = []

	class TrackingRegistry(PackageRegistry):
		def _increment_downloads(self, package: Any) -> None:
			calls.append((package.name, package.version))
			# Still mutate in-memory so tests that read package.downloads
			# observe the bump.
			super()._increment_downloads(package)

	registry = TrackingRegistry(_signing_port())
	_publish_signed(registry)

	trust = TrustConfig(trusted_signing_keys=[{"id": "test-key"}])
	for _ in range(5):
		_drive(registry.install("acme.demo", "1.0.0", trust=trust))

	assert calls == [("acme.demo", "1.0.0")] * 5


def test_JH_02_counter_converges_across_two_replicas() -> None:
	"""Two PackageRegistry replicas pointed at the same shared store
	(simulating a DB) converge to a single counter — 100 installs each
	→ shared store shows 200."""

	from flowforge_jtbd_hub.registry import Package, PackageRegistry
	from flowforge_jtbd_hub.trust import TrustConfig

	# Shared "DB": a single dict[name@version, downloads_int].
	shared_db: dict[tuple[str, str], int] = {}

	class SharedDbRegistry(PackageRegistry):
		def _increment_downloads(self, package: Any) -> None:
			key = (package.name, package.version)
			shared_db[key] = shared_db.get(key, 0) + 1
			# Reflect the shared count into the in-memory package so
			# subsequent reads see the converged value.
			package.downloads = shared_db[key]

	signing = _signing_port()
	r1 = SharedDbRegistry(signing)
	r2 = SharedDbRegistry(signing)

	# Publish once on r1 then mirror to r2 so both have the package row.
	signed = _publish_signed(r1)
	# r2 sees the same publish — mimic by storing the package directly.
	pkg = r1._load_package(signed.name, signed.version)
	assert pkg is not None
	r2._store_package(
		Package(
			manifest=pkg.manifest,
			bundle=pkg.bundle,
			published_at=pkg.published_at,
			signed_at_publish=pkg.signed_at_publish,
		)
	)

	trust = TrustConfig(trusted_signing_keys=[{"id": "test-key"}])

	async def install_n(reg: PackageRegistry, n: int) -> None:
		for _ in range(n):
			await reg.install(signed.name, signed.version, trust=trust)

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(asyncio.gather(install_n(r1, 100), install_n(r2, 100)))
	finally:
		loop.close()

	assert shared_db[(signed.name, signed.version)] == 200


# ---------------------------------------------------------------------------
# JH-03 — verified_at_install cache
# ---------------------------------------------------------------------------


def test_JH_03_verified_at_install_set_on_first_install() -> None:
	"""The first install of a signed package sets
	``package.verified_at_install`` to the current clock."""

	from flowforge_jtbd_hub.registry import PackageRegistry
	from flowforge_jtbd_hub.trust import TrustConfig

	registry = PackageRegistry(_signing_port())
	_publish_signed(registry)

	pkg_before = registry._load_package("acme.demo", "1.0.0")
	assert pkg_before is not None and pkg_before.verified_at_install is None

	trust = TrustConfig(trusted_signing_keys=[{"id": "test-key"}])
	_drive(registry.install("acme.demo", "1.0.0", trust=trust))

	pkg_after = registry._load_package("acme.demo", "1.0.0")
	assert pkg_after is not None
	assert pkg_after.verified_at_install is not None
	assert isinstance(pkg_after.verified_at_install, datetime)


def test_JH_03_subsequent_install_skips_reverify_within_window() -> None:
	"""Within the 24h reverify window, install does not re-call
	``verify_manifest`` — the cached ``verified_at_install`` short-circuits."""

	from flowforge_jtbd_hub import registry as registry_mod
	from flowforge_jtbd_hub.registry import PackageRegistry
	from flowforge_jtbd_hub.trust import TrustConfig

	registry = PackageRegistry(_signing_port())
	_publish_signed(registry)

	# First install populates the cache.
	trust = TrustConfig(trusted_signing_keys=[{"id": "test-key"}])
	_drive(registry.install("acme.demo", "1.0.0", trust=trust))

	# Patch verify_manifest to fail; second install must short-circuit.
	original = registry_mod.verify_manifest
	calls = {"count": 0}

	async def boom(*args: Any, **kwargs: Any) -> bool:
		calls["count"] += 1
		raise AssertionError("verify_manifest should NOT be called within cache window")

	registry_mod.verify_manifest = boom  # type: ignore[assignment]
	try:
		_drive(registry.install("acme.demo", "1.0.0", trust=trust))
	finally:
		registry_mod.verify_manifest = original  # type: ignore[assignment]

	assert calls["count"] == 0


def test_JH_03_reverify_required_outside_cache_window() -> None:
	"""When ``verified_at_install`` is older than the cache window,
	the install reverifies."""

	from flowforge_jtbd_hub.registry import PackageRegistry
	from flowforge_jtbd_hub.trust import TrustConfig

	registry = PackageRegistry(_signing_port())
	_publish_signed(registry)

	# Force the cache stamp to be in the distant past.
	pkg = registry._load_package("acme.demo", "1.0.0")
	assert pkg is not None
	pkg.verified_at_install = datetime.now(timezone.utc) - timedelta(days=8)

	# Re-install: must succeed (re-verifies).
	trust = TrustConfig(trusted_signing_keys=[{"id": "test-key"}])
	_drive(registry.install("acme.demo", "1.0.0", trust=trust))

	# Cache stamp is refreshed to ~now.
	pkg2 = registry._load_package("acme.demo", "1.0.0")
	assert pkg2 is not None
	assert pkg2.verified_at_install is not None
	delta = datetime.now(timezone.utc) - pkg2.verified_at_install
	assert delta < timedelta(seconds=5)


# ---------------------------------------------------------------------------
# JH-04 — admin token rotation
# ---------------------------------------------------------------------------


def test_JH_04_admin_token_accepts_any_in_csv_list() -> None:
	"""``create_app(admin_token=...)`` accepts a comma-separated list;
	any one of the tokens authenticates an admin call."""

	from fastapi.testclient import TestClient

	from flowforge_jtbd_hub.app import create_app
	from flowforge_jtbd_hub.registry import PackageRegistry

	registry = PackageRegistry(_signing_port())
	app = create_app(registry, admin_token="rotating,old-token,new-token")
	client = TestClient(app)

	# Each token in the rotation list authenticates.
	for token in ("rotating", "old-token", "new-token"):
		resp = client.post(
			"/api/jtbd-hub/packages/x/1/demote",
			json={"reason": "test"},
			headers={"Authorization": f"Bearer {token}"},
		)
		# Admin auth passes (404 because package doesn't exist, not 401).
		assert resp.status_code != 401, f"{token!r} rejected; got {resp.status_code}"

	# A non-listed token is rejected.
	resp = client.post(
		"/api/jtbd-hub/packages/x/1/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer not-in-list"},
	)
	assert resp.status_code == 401


def test_JH_04_admin_token_single_value_still_works() -> None:
	"""Backward compat: a single token (no commas) still authenticates."""

	from fastapi.testclient import TestClient

	from flowforge_jtbd_hub.app import create_app
	from flowforge_jtbd_hub.registry import PackageRegistry

	registry = PackageRegistry(_signing_port())
	app = create_app(registry, admin_token="just-one")
	client = TestClient(app)

	resp = client.post(
		"/api/jtbd-hub/packages/x/1/demote",
		json={"reason": "test"},
		headers={"Authorization": "Bearer just-one"},
	)
	assert resp.status_code != 401


# ---------------------------------------------------------------------------
# JH-05 — platformdirs paths
# ---------------------------------------------------------------------------


def test_JH_05_uses_platformdirs_for_user_path() -> None:
	"""``_USER_TRUST_PATH`` is derived from
	:func:`platformdirs.user_config_dir` so Windows / macOS / Linux pick
	up the platform-correct path."""

	import inspect

	from flowforge_jtbd_hub import trust as trust_mod

	src = inspect.getsource(trust_mod)
	assert "platformdirs" in src, (
		"trust.py must use platformdirs for cross-platform path resolution (JH-05)"
	)
	# Sanity: the resolved path is a Path and contains "flowforge".
	assert isinstance(trust_mod._USER_TRUST_PATH, Path)
	assert "flowforge" in str(trust_mod._USER_TRUST_PATH).lower()


def test_JH_05_uses_platformdirs_for_system_path() -> None:
	from flowforge_jtbd_hub import trust as trust_mod

	assert isinstance(trust_mod._SYSTEM_TRUST_PATH, Path)
	assert "flowforge" in str(trust_mod._SYSTEM_TRUST_PATH).lower()


# ---------------------------------------------------------------------------
# JH-06 — pydantic-only except narrowing
# ---------------------------------------------------------------------------


def test_JH_06_load_yaml_trust_narrows_to_validation_error(tmp_path: Path) -> None:
	"""Malformed YAML schema raises TrustConfigError chained from
	pydantic.ValidationError; OOM and KeyboardInterrupt propagate."""

	from flowforge_jtbd_hub.trust import TrustConfigError, _load_yaml_trust

	bad = tmp_path / "bad.yaml"
	bad.write_text("trusted_signing_keys: not-a-list\n")
	with pytest.raises(TrustConfigError) as exc_info:
		_load_yaml_trust(bad)
	# __cause__ should be a pydantic ValidationError, not a generic Exception.
	from pydantic import ValidationError

	assert isinstance(exc_info.value.__cause__, ValidationError)


def test_JH_06_load_yaml_trust_does_not_swallow_keyboardinterrupt(
	tmp_path: Path,
) -> None:
	"""KeyboardInterrupt raised inside ``model_validate`` propagates
	(does not get re-wrapped as TrustConfigError)."""

	import flowforge_jtbd_hub.trust as trust_mod

	good = tmp_path / "good.yaml"
	good.write_text("trusted_signing_keys: []\n")

	original = trust_mod.TrustConfig.model_validate

	def kaboom(*args: Any, **kwargs: Any) -> Any:
		raise KeyboardInterrupt("synthetic")

	trust_mod.TrustConfig.model_validate = staticmethod(kaboom)  # type: ignore[assignment]
	try:
		with pytest.raises(KeyboardInterrupt):
			trust_mod._load_yaml_trust(good)
	finally:
		trust_mod.TrustConfig.model_validate = original  # type: ignore[assignment]


def test_JH_06_load_pyproject_trust_narrows_to_validation_error(tmp_path: Path) -> None:
	"""Same narrowing applies to the pyproject.toml loader."""

	from flowforge_jtbd_hub.trust import TrustConfigError, _load_pyproject_trust

	bad = tmp_path / "pyproject.toml"
	bad.write_text(
		'[tool.flowforge.trust]\n'
		'trusted_signing_keys = "not-a-list"\n'
	)
	with pytest.raises(TrustConfigError) as exc_info:
		_load_pyproject_trust(bad)
	from pydantic import ValidationError

	assert isinstance(exc_info.value.__cause__, ValidationError)
