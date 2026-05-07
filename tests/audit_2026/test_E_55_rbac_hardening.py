"""E-55 — RBAC hardening regression tests (RB-01, RB-02).

Audit reference: framework/docs/audit-fix-plan.md §7 E-55.

- **RB-01 (P2)** — ``StaticRbac.from_yaml/from_json`` previously read the
  caller-supplied path verbatim. A workflow that took a config path from
  user input would let ``../../etc/passwd`` succeed. Fix: opt-in
  ``allowed_root`` parameter; when set, the resolved path must be inside
  that root or ``ValueError`` is raised before any read.

- **RB-02 (P2)** — ``SpiceDBRbac`` did not propagate the ``Zedtoken``
  written by ``WriteRelationships`` into subsequent ``CheckPermission``
  calls, so a write-then-immediate-read could miss the new relation
  (SpiceDB's ``minimize_latency`` default). Fix: cache the most recent
  ``written_at_token`` and pass it as ``consistency.at_least_as_fresh``
  on every read, giving read-after-write consistency.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# RB-01 — StaticRbac path traversal
# ---------------------------------------------------------------------------


def _make_yaml(tmp_path: Path) -> Path:
	body = (
		"roles:\n"
		"  clerk: [claim.create]\n"
		"principals:\n"
		"  alice: [clerk]\n"
		"permissions:\n"
		"  - {name: claim.create, description: 'submit claim'}\n"
	)
	cfg = tmp_path / "rbac.yaml"
	cfg.write_text(body, encoding="utf-8")
	return cfg


def test_RB_01_path_inside_allowed_root_loads(tmp_path: Path) -> None:
	from flowforge_rbac_static import StaticRbac

	cfg = _make_yaml(tmp_path)
	r = StaticRbac.from_yaml(cfg, allowed_root=tmp_path)
	assert r is not None


def test_RB_01_path_traversal_outside_root_rejected(tmp_path: Path) -> None:
	"""``../../etc/passwd``-style escape from the allowed root raises ``ValueError``."""
	from flowforge_rbac_static import StaticRbac

	cfg = _make_yaml(tmp_path)

	# Plant the actual file outside the allowed root via parent dir.
	allowed_root = tmp_path / "allowed"
	allowed_root.mkdir()
	# cfg is *not* under allowed_root.
	with pytest.raises(ValueError):
		StaticRbac.from_yaml(cfg, allowed_root=allowed_root)

	# Same for traversal-style paths constructed by string concat.
	with pytest.raises(ValueError):
		StaticRbac.from_yaml(
			str(allowed_root / ".." / "rbac.yaml"),
			allowed_root=allowed_root,
		)

	# json variant has the same gate.
	json_cfg = tmp_path / "rbac.json"
	json_cfg.write_text('{"roles":{},"principals":{},"permissions":[]}', encoding="utf-8")
	with pytest.raises(ValueError):
		StaticRbac.from_json(json_cfg, allowed_root=allowed_root)


def test_RB_01_no_allowed_root_keeps_legacy_behaviour(tmp_path: Path) -> None:
	"""Backward-compat: omitting ``allowed_root`` accepts any path (legacy)."""
	from flowforge_rbac_static import StaticRbac

	cfg = _make_yaml(tmp_path)
	# No allowed_root — legacy callers keep working.
	r = StaticRbac.from_yaml(cfg)
	assert r is not None


# ---------------------------------------------------------------------------
# RB-02 — SpiceDB Zedtoken propagation
# ---------------------------------------------------------------------------


def _run(coro):
	loop = asyncio.new_event_loop()
	try:
		return loop.run_until_complete(coro)
	finally:
		loop.close()


def test_RB_02_zedtoken_captured_on_write() -> None:
	"""``register_permission`` (which writes relationships) caches the token."""
	from flowforge_rbac_spicedb import SpiceDBRbac
	from flowforge_rbac_spicedb.testing import FakeSpiceDBClient

	client = FakeSpiceDBClient()
	rbac = SpiceDBRbac(client=client)

	assert rbac.last_zedtoken() is None
	_run(rbac.register_permission("claim.create", "submit claim"))
	# Fake returns "fake-zedtoken"; resolver must surface it.
	assert rbac.last_zedtoken() == "fake-zedtoken"


def test_RB_02_zedtoken_propagated_to_check() -> None:
	"""After a write, every CheckPermission carries ``at_least_as_fresh``."""
	from flowforge_rbac_spicedb import SpiceDBRbac
	from flowforge_rbac_spicedb.testing import FakeSpiceDBClient
	from flowforge.ports import Principal, Scope

	client = FakeSpiceDBClient()
	rbac = SpiceDBRbac(client=client)

	# Write triggers Zedtoken capture.
	_run(rbac.register_permission("claim.create", "submit claim"))

	# Issue a CheckPermission — fake records the consistency it received.
	_run(
		rbac.has_permission(
			Principal(user_id="alice"),
			"claim.create",
			Scope(tenant_id="t-1"),
		)
	)

	# Last CheckPermission saw the Zedtoken via consistency.at_least_as_fresh.
	last = client.last_consistency_token
	assert last == "fake-zedtoken", (
		f"CheckPermission did not propagate Zedtoken (got {last!r})"
	)


def test_RB_02_zedtoken_cleared_after_explicit_reset() -> None:
	"""``reset_zedtoken()`` lets callers opt out of strict consistency.

	Useful in batched read-only contexts where the small staleness is
	acceptable and the latency saving matters.
	"""
	from flowforge_rbac_spicedb import SpiceDBRbac
	from flowforge_rbac_spicedb.testing import FakeSpiceDBClient

	client = FakeSpiceDBClient()
	rbac = SpiceDBRbac(client=client)
	_run(rbac.register_permission("claim.create", "submit claim"))
	assert rbac.last_zedtoken() == "fake-zedtoken"
	rbac.reset_zedtoken()
	assert rbac.last_zedtoken() is None


def test_RB_02_no_zedtoken_before_first_write() -> None:
	"""CheckPermission before any write sends no consistency hint."""
	from flowforge_rbac_spicedb import SpiceDBRbac
	from flowforge_rbac_spicedb.testing import FakeSpiceDBClient
	from flowforge.ports import Principal, Scope

	client = FakeSpiceDBClient()
	rbac = SpiceDBRbac(client=client)
	_run(
		rbac.has_permission(
			Principal(user_id="alice"),
			"claim.create",
			Scope(tenant_id="t-1"),
		)
	)
	assert client.last_consistency_token is None
