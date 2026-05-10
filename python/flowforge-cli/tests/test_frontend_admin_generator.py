"""Tests for the per-bundle frontend_admin generator (W2 / item 15).

Coverage:

* Generator emits the expected fixed set of files under
  ``frontend-admin/<package>/`` regardless of how many JTBDs the bundle
  declares (per-bundle aggregation, plan §1 principle 2).
* Synthesized admin permission catalog matches the W0 per-JTBD shape
  and is sorted/deterministic.
* TypeScript strict tsconfig flags are present.
* Generator output is byte-identical across two invocations against
  the same bundle (Principle 1).
* Admin app is invariant under the ``form_renderer`` flag — flipping
  ``project.frontend.form_renderer`` between ``"skeleton"`` and
  ``"real"`` does not change a single byte under
  ``frontend-admin/``.
* CONSUMES is mirrored in the fixture-registry primer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import frontend_admin as gen
from flowforge_cli.jtbd.normalize import normalize


REPO_ROOT = Path(__file__).resolve().parents[3]
_INSURANCE_BUNDLE = REPO_ROOT / "examples" / "insurance_claim" / "jtbd-bundle.json"
_BUILDING_BUNDLE = REPO_ROOT / "examples" / "building-permit" / "jtbd-bundle.json"
_HIRING_BUNDLE = REPO_ROOT / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


# Files every admin app must include — keyed off the canonical layout
# the generator advertises. If anyone renames a page, this fails first.
EXPECTED_REL_PATHS: tuple[str, ...] = (
	"README.md",
	"index.html",
	"package.json",
	"src/App.tsx",
	"src/api.ts",
	"src/main.tsx",
	"src/pages/AuditLogViewer.tsx",
	"src/pages/InstanceBrowser.tsx",
	"src/pages/OutboxQueue.tsx",
	"src/pages/PermissionsHistory.tsx",
	"src/pages/RlsLog.tsx",
	"src/pages/SagaPanel.tsx",
	"src/permissions.ts",
	"tsconfig.json",
	"vite.config.ts",
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def _admin_files(files: list[Any]) -> list[Any]:
	return [f for f in files if f.path.startswith("frontend-admin/")]


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_full_app_tree_under_package_dir() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	root = f"frontend-admin/{bundle.project.package}"
	rel = sorted(f.path[len(root) + 1 :] for f in out)
	assert rel == sorted(EXPECTED_REL_PATHS)
	assert all(f.path.startswith(root + "/") for f in out)


def test_aggregates_one_app_per_bundle_not_per_jtbd() -> None:
	# building-permit has 5 JTBDs; the admin app is still a single tree.
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	# Same set of files as the single-JTBD bundle — count is JTBD-agnostic.
	assert len(out) == len(EXPECTED_REL_PATHS)


def test_admin_permissions_synthesized_per_jtbd() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	perms = gen._admin_permissions(bundle)
	# 4 admin perms per JTBD (read, compensate, outbox.retry, grant);
	# insurance has 1 JTBD => 4 perms total, sorted.
	assert perms == (
		"admin.claim_intake.compensate",
		"admin.claim_intake.grant",
		"admin.claim_intake.outbox.retry",
		"admin.claim_intake.read",
	)


def test_admin_permissions_sorted_for_multi_jtbd() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	perms = gen._admin_permissions(bundle)
	# 5 JTBDs * 4 perms each = 20.
	assert len(perms) == 5 * 4
	# All entries sorted (deterministic emission).
	assert list(perms) == sorted(perms)
	# Every perm is admin-prefixed.
	assert all(p.startswith("admin.") for p in perms)


def test_permissions_ts_lists_all_admin_perms() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(perms_file,) = [f for f in out if f.path.endswith("/src/permissions.ts")]
	for p in gen._admin_permissions(bundle):
		assert f'"{p}"' in perms_file.content


def test_app_tsx_router_lists_six_pages() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(app_tsx,) = [f for f in out if f.path.endswith("/src/App.tsx")]
	for page_id in ("instances", "audit", "saga", "grants", "outbox", "rls"):
		assert f'id: "{page_id}"' in app_tsx.content


def test_tsconfig_uses_typescript_strict_mode() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(ts,) = [f for f in out if f.path.endswith("/tsconfig.json")]
	cfg = json.loads(ts.content)
	co = cfg["compilerOptions"]
	# Hard strict-mode flags the admin app must keep.
	assert co["strict"] is True
	assert co["noUncheckedIndexedAccess"] is True
	assert co["exactOptionalPropertyTypes"] is True
	assert co["useUnknownInCatchVariables"] is True
	assert co["forceConsistentCasingInFileNames"] is True


def test_package_json_declares_react_18_and_vite_5() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(pkg,) = [f for f in out if f.path.endswith("/package.json")]
	manifest = json.loads(pkg.content)
	assert manifest["dependencies"]["react"].startswith("^18.")
	assert manifest["dependencies"]["react-dom"].startswith("^18.")
	assert manifest["devDependencies"]["vite"].startswith("^5.")
	# build script must run typecheck via tsc -b before vite build, so
	# a TS-strict regression breaks the host's build.
	assert manifest["scripts"]["build"] == "tsc -b && vite build"


def test_readme_documents_postgres_assumption() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(readme,) = [f for f in out if f.path.endswith("/README.md")]
	# PG-only assumption note (plan §11) and the named adapters.
	assert "Postgres assumption" in readme.content
	assert "flowforge-audit-pg" in readme.content
	assert "flowforge-outbox-pg" in readme.content
	assert "Non-Postgres" in readme.content


def test_audit_viewer_lists_bundle_audit_topics() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	(viewer,) = [f for f in out if f.path.endswith("/src/pages/AuditLogViewer.tsx")]
	# Every audit topic the bundle aggregates lands in the viewer's
	# AUDIT_TOPICS const.
	for topic in bundle.all_audit_topics:
		assert f'"{topic}"' in viewer.content


# ---------------------------------------------------------------------------
# Determinism (Principle 1 + plan §6 cumulative gate)
# ---------------------------------------------------------------------------


def test_deterministic_output_insurance_claim() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert [(f.path, f.content) for f in first] == [
		(f.path, f.content) for f in second
	]


def test_deterministic_output_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert [(f.path, f.content) for f in first] == [
		(f.path, f.content) for f in second
	]


def test_deterministic_output_hiring_pipeline() -> None:
	bundle = _load_normalized(_HIRING_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert [(f.path, f.content) for f in first] == [
		(f.path, f.content) for f in second
	]


# ---------------------------------------------------------------------------
# Form-renderer flag invariance — admin app must not depend on it.
# ---------------------------------------------------------------------------


def _flip_form_renderer(raw: dict[str, Any], value: str) -> dict[str, Any]:
	# Deep-ish copy via json round-trip; the bundle is JSON-serialisable.
	clone = json.loads(json.dumps(raw))
	clone.setdefault("project", {}).setdefault("frontend", {})
	clone["project"]["frontend"]["form_renderer"] = value
	return clone


def test_admin_app_byte_identical_across_form_renderer_flag() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	skel = generate(_flip_form_renderer(raw, "skeleton"))
	real = generate(_flip_form_renderer(raw, "real"))
	skel_admin = {f.path: f.content for f in skel if f.path.startswith("frontend-admin/")}
	real_admin = {f.path: f.content for f in real if f.path.startswith("frontend-admin/")}
	assert skel_admin == real_admin


# ---------------------------------------------------------------------------
# Pipeline integration — generator wired through ``generate``.
# ---------------------------------------------------------------------------


def test_pipeline_includes_frontend_admin_files() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	files = generate(raw)
	admin = _admin_files(files)
	pkg = raw["project"]["package"]
	# Other per-bundle generators (v0.3.0 W3 / item 18 design tokens)
	# contribute additional files to the admin tree for theme parity.
	# This test pins the frontend_admin generator's own contribution, so
	# subtract those out before comparing against EXPECTED_REL_PATHS.
	design_token_paths = {
		"src/design_tokens.css",
		"src/theme.ts",
		"tailwind.config.ts",
	}
	rel = sorted(
		path
		for f in admin
		for path in [f.path[len(f"frontend-admin/{pkg}/") :]]
		if path not in design_token_paths
	)
	assert rel == sorted(EXPECTED_REL_PATHS)


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("frontend_admin")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_frontend_admin() -> None:
	assert "frontend_admin" in _fixture_registry.all_generators()
