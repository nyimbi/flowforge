"""Emit deterministic alembic migrations for one JTBD's tables.

W0 (audit-2026 baseline): single migration creating the entity table.
W2 / item 6 (router-level idempotency keys): a second migration creating
the per-JTBD ``<table>_idempotency_keys`` table with a
``UNIQUE(tenant_id, idempotency_key)`` constraint and a TTL-shaped
``expires_at`` column. The two migrations chain so the entity table's
revision id is the ``down_revision`` of the idempotency keys migration —
existing entity migration bytes stay byte-identical, the new migration
appears alongside.
"""

from __future__ import annotations

import hashlib

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bundle paths this generator reads — declared so the fixture-coverage
# audit can confirm at least one example exercises every input field.
CONSUMES: tuple[str, ...] = (
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].required",
	"jtbds[].fields[].sa_type",
	"jtbds[].id",
	"jtbds[].initial_state",
	"jtbds[].table_name",
	"jtbds[].title",
	"project.package",
)


def _stable_revision(bundle_pkg: str, jtbd_id: str, suffix: str | None = None) -> str:
	"""Return a 12-char hex revision id derived from package + id (+ suffix).

	Deterministic so two runs of the generator emit identical migrations.
	The optional *suffix* lets us derive a fresh revision id for chained
	migrations (e.g. the W2 idempotency_keys table) without colliding
	with the entity migration's id. Pre-W2 callers omit the suffix and
	get the original byte-identical hash.
	"""

	if suffix is None:
		key = f"{bundle_pkg}:{jtbd_id}"
	else:
		key = f"{bundle_pkg}:{jtbd_id}:{suffix}"
	digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
	return digest[:12]


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> list[GeneratedFile]:
	"""Emit the entity-table migration and the chained idempotency_keys migration."""

	entity_revision = _stable_revision(bundle.project.package, jtbd.id)
	entity_content = render(
		"db_migration.py.j2",
		project=bundle.project,
		jtbd=jtbd,
		revision=entity_revision,
	)
	entity_file = GeneratedFile(
		path=f"backend/migrations/versions/{entity_revision}_create_{jtbd.table_name}.py",
		content=entity_content,
	)

	# v0.3.0 W2 (item 6): chained per-JTBD idempotency_keys migration.
	# The revision id is derived from a distinct suffix so the entity
	# migration's id is unchanged byte-for-byte.
	idem_revision = _stable_revision(
		bundle.project.package, jtbd.id, suffix="idempotency_keys"
	)
	idem_content = render(
		"db_migration_idempotency_keys.py.j2",
		project=bundle.project,
		jtbd=jtbd,
		revision=idem_revision,
		down_revision=entity_revision,
	)
	idem_file = GeneratedFile(
		path=(
			f"backend/migrations/versions/"
			f"{idem_revision}_create_{jtbd.table_name}_idempotency_keys.py"
		),
		content=idem_content,
	)

	return [entity_file, idem_file]
