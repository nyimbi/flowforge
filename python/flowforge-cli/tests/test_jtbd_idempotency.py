"""Unit tests for v0.3.0 W2 / item 6 — router-level idempotency keys.

Covers:

* The chained ``db_migration`` generator emits BOTH the entity-table
  migration and the per-JTBD ``<table>_idempotency_keys`` migration with
  a UNIQUE(tenant_id, idempotency_key) constraint.
* Existing entity-table migration revisions stay byte-identical (the
  W2-introduced suffix only affects the chained idempotency-keys file).
* The new per-JTBD ``idempotency`` generator emits a helper module under
  ``backend/src/<pkg>/<jtbd>/idempotency.py`` and threads
  ``project.idempotency.ttl_hours`` through to the generated
  ``IDEMPOTENCY_TTL_HOURS`` constant. Default ``None`` → 24h.
* The ``domain_router.py.j2`` template enforces the
  ``Idempotency-Key`` header gate (400 / 409 / cached 200) and pulls in
  the helpers from the per-JTBD module.
* Byte-deterministic regen across two pipeline runs even with the
  custom-TTL bundle override.
* The fixture-coverage registry agrees with the generators' ``CONSUMES``
  declarations.
"""

from __future__ import annotations

import compileall
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry, db_migration, idempotency
from flowforge_cli.jtbd.normalize import normalize


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _bundle(ttl_hours: int | None = None) -> dict[str, Any]:
	"""Tiny single-JTBD bundle exercising the idempotency surface."""

	bundle: dict[str, Any] = {
		"project": {
			"name": "idem-demo",
			"package": "idem_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {"roles": ["adjuster"], "permissions": []},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["queued within 24h"],
				"data_capture": [
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant",
						"required": True,
						"pii": True,
					},
				],
			}
		],
	}
	if ttl_hours is not None:
		bundle["project"]["idempotency"] = {"ttl_hours": ttl_hours}
	return bundle


# ---------------------------------------------------------------------------
# db_migration: chained pair
# ---------------------------------------------------------------------------


def test_db_migration_emits_entity_and_idempotency_keys_pair() -> None:
	"""The W2 db_migration emits two files per JTBD: entity + idempotency_keys."""

	files = generate(_bundle())
	migrations = [
		f
		for f in files
		if f.path.startswith("backend/migrations/versions/")
		and f.path.endswith(".py")
	]
	# exactly two migrations per JTBD: entity-table + chained idempotency_keys
	assert len(migrations) == 2, [f.path for f in migrations]

	(entity,) = [f for f in migrations if "_idempotency_keys" not in f.path]
	(idem,) = [f for f in migrations if f.path.endswith("_idempotency_keys.py")]

	# entity-table migration unchanged surface (still creates the entity table)
	assert "claim_intake" in entity.content
	assert "claim_intake_idempotency_keys" not in entity.content

	# idempotency_keys migration carries the UNIQUE constraint and chains to entity
	assert "UniqueConstraint" in idem.content
	assert '"tenant_id"' in idem.content
	assert '"idempotency_key"' in idem.content
	assert "claim_intake_idempotency_keys" in idem.content
	# down_revision points at the entity-table revision (chained)
	entity_rev = entity.path.split("/")[-1].split("_create_")[0]
	assert f'down_revision = "{entity_rev}"' in idem.content


def test_entity_migration_revision_is_unchanged_byte_for_byte() -> None:
	"""The W2 chained-suffix change must not perturb the entity revision id.

	Revision ids are baked into ``alembic_version`` rows on deployed hosts;
	a hash drift would force every host to fork a re-tag migration.
	"""

	# Reproduce the pre-W2 hash directly: ``sha256("<pkg>:<jtbd>")[:12]``.
	import hashlib

	expected = hashlib.sha256(b"idem_demo:claim_intake").hexdigest()[:12]
	got = db_migration._stable_revision("idem_demo", "claim_intake")
	assert got == expected, f"entity revision drift: expected={expected} got={got}"


def test_idempotency_keys_revision_is_distinct_from_entity() -> None:
	entity_rev = db_migration._stable_revision("idem_demo", "claim_intake")
	idem_rev = db_migration._stable_revision(
		"idem_demo", "claim_intake", suffix="idempotency_keys"
	)
	assert entity_rev != idem_rev


# ---------------------------------------------------------------------------
# idempotency generator
# ---------------------------------------------------------------------------


def test_idempotency_helper_emitted_per_jtbd() -> None:
	files = generate(_bundle())
	(helper,) = [
		f for f in files if f.path == "backend/src/idem_demo/claim_intake/idempotency.py"
	]
	# Constants the router pulls in
	assert "IDEMPOTENCY_TABLE: str = \"claim_intake_idempotency_keys\"" in helper.content
	# Default TTL is 24h
	assert "IDEMPOTENCY_TTL_HOURS: int = 24" in helper.content
	# Helper exposes the three callables the router uses
	assert "fingerprint_request" in helper.content
	assert "check_idempotency_key" in helper.content
	assert "record_idempotency_response" in helper.content


def test_idempotency_ttl_overrides_default() -> None:
	files = generate(_bundle(ttl_hours=48))
	(helper,) = [
		f for f in files if f.path.endswith("/claim_intake/idempotency.py")
	]
	assert "IDEMPOTENCY_TTL_HOURS: int = 48" in helper.content


def test_idempotency_helper_compiles(tmp_path: Path) -> None:
	files = generate(_bundle())
	(helper,) = [
		f for f in files if f.path.endswith("/claim_intake/idempotency.py")
	]
	dst = tmp_path / "idempotency.py"
	dst.write_text(helper.content, encoding="utf-8")
	assert compileall.compile_file(str(dst), quiet=1)


# ---------------------------------------------------------------------------
# router gate
# ---------------------------------------------------------------------------


def test_router_enforces_idempotency_key_header() -> None:
	files = generate(_bundle())
	(router,) = [
		f for f in files if f.path.endswith("/routers/claim_intake_router.py")
	]
	# Required tokens for the W2b ratchet to pass
	assert "Idempotency-Key" in router.content
	assert "check_idempotency_key" in router.content
	assert "record_idempotency_response" in router.content
	assert "HTTP_400_BAD_REQUEST" in router.content
	assert "HTTP_409_CONFLICT" in router.content
	# Replay surfaces the cached body with the marker
	assert "_idempotent_replay" in router.content


def test_router_imports_helper_from_per_jtbd_module() -> None:
	files = generate(_bundle())
	(router,) = [
		f for f in files if f.path.endswith("/routers/claim_intake_router.py")
	]
	assert "from ..claim_intake.idempotency import" in router.content


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_idempotency_pipeline_is_byte_deterministic() -> None:
	a = generate(_bundle())
	b = generate(_bundle())
	assert [f.path for f in a] == [f.path for f in b]
	for fa, fb in zip(a, b, strict=True):
		assert fa.content == fb.content, f"non-deterministic: {fa.path}"


def test_idempotency_pipeline_is_byte_deterministic_with_custom_ttl() -> None:
	a = generate(_bundle(ttl_hours=72))
	b = generate(_bundle(ttl_hours=72))
	assert [f.path for f in a] == [f.path for f in b]
	for fa, fb in zip(a, b, strict=True):
		assert fa.content == fb.content, f"non-deterministic: {fa.path}"


# ---------------------------------------------------------------------------
# normalize wires through
# ---------------------------------------------------------------------------


def test_normalize_carries_ttl_through_view_model() -> None:
	norm = normalize(_bundle(ttl_hours=12))
	assert norm.project.idempotency_ttl_hours == 12

	norm_default = normalize(_bundle())
	assert norm_default.project.idempotency_ttl_hours is None


# ---------------------------------------------------------------------------
# fixture-registry coverage
# ---------------------------------------------------------------------------


def test_idempotency_consumes_matches_registry() -> None:
	declared = idempotency.CONSUMES
	registered = _fixture_registry.get("idempotency")
	assert tuple(sorted(declared)) == tuple(sorted(registered)), (declared, registered)


def test_db_migration_consumes_matches_registry() -> None:
	declared = db_migration.CONSUMES
	registered = _fixture_registry.get("db_migration")
	assert tuple(sorted(declared)) == tuple(sorted(registered)), (declared, registered)
