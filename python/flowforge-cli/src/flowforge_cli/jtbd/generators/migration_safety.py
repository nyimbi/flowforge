"""Per-bundle generator: emit ``backend/migrations/safety/<rev>.md``.

For every generated alembic migration (one per JTBD), produce a static
safety report covering:

* severity classification (INFO / WARN / HIGH / CRITICAL),
* blast radius (table, columns, deployed-instance implications),
* suggested rewrites for each forward-looking risk class.

The initial migration this generator describes is always a fresh
``CREATE TABLE``; that operation has no live-data risk so the headline
severity is INFO. The interesting content is the *forward-looking risk
register* — the same table will accumulate column-add / column-drop /
type-narrow / index-add migrations over its life, and each of those
operations is the actual incident-class catcher. The static report
gives operators the suggested-rewrite recipe at the same generation-
time touchpoint as the initial migration itself.

Item 1 of :doc:`docs/improvements`, W0 of
:doc:`docs/v0.3.0-engineering-plan`. The standalone analyzer that
operates on already-emitted migrations lives in
:mod:`flowforge_cli.commands.migration_safety` and shares the same rule
catalogue.

The fixture-registry primer at :mod:`._fixture_registry` records the
attribute paths this generator reads; the bidirectional coverage test
(Pre-mortem Scenario 1) cross-checks generator and registry.
"""

from __future__ import annotations

import hashlib

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].kind",
	"jtbds[].fields[].required",
	"jtbds[].fields[].sa_type",
	"jtbds[].id",
	"jtbds[].initial_state",
	"jtbds[].table_name",
	"jtbds[].title",
	"project.package",
)


def _stable_revision(bundle_pkg: str, jtbd_id: str) -> str:
	"""Mirror :func:`flowforge_cli.jtbd.generators.db_migration._stable_revision`.

	Re-implemented locally so this generator does not depend on the
	import order of its sibling. The hash space is the same, so the
	revision id in the report matches the revision id of the migration
	the report is *about*.
	"""

	digest = hashlib.sha256(f"{bundle_pkg}:{jtbd_id}".encode("utf-8")).hexdigest()
	return digest[:12]


def _safety_view(jtbd: NormalizedJTBD) -> dict[str, object]:
	"""Build a deterministic, sorted view of the JTBD's column shape."""

	# Sort by id so two runs produce the same template render. The
	# normalizer already keeps a fixed order (declaration order from the
	# bundle), but anchoring on a sorted view inside this generator makes
	# the determinism boundary explicit and survives any future re-order
	# in the normalizer.
	required = []
	nullable = []
	for f in sorted(jtbd.fields, key=lambda x: x.id):
		entry = {
			"id": f.id,
			"kind": f.kind,
			"sa_type": f.sa_type,
		}
		if f.required:
			required.append(entry)
		else:
			nullable.append(entry)
	return {
		"required": required,
		"nullable": nullable,
		"required_count": len(required),
		"nullable_count": len(nullable),
	}


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit one safety report per JTBD migration.

	Per-bundle generator (runs once over the whole bundle), but emits
	one file per JTBD because each JTBD owns its own alembic revision.
	Returning a list keeps the pipeline's ``_coerce`` happy.
	"""

	out: list[GeneratedFile] = []
	# Sort JTBDs by id so the emission order is stable regardless of
	# bundle declaration order.
	for jt in sorted(bundle.jtbds, key=lambda j: j.id):
		revision = _stable_revision(bundle.project.package, jt.id)
		view = _safety_view(jt)
		content = render(
			"migration_safety.md.j2",
			project=bundle.project,
			jtbd=jt,
			revision=revision,
			required_fields=view["required"],
			nullable_fields=view["nullable"],
			required_count=view["required_count"],
			nullable_count=view["nullable_count"],
		)
		out.append(
			GeneratedFile(
				path=f"backend/migrations/safety/{revision}.md",
				content=content,
			)
		)
	return out
