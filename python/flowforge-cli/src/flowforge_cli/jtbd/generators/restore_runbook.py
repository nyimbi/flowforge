"""Per-bundle generator: emit ``docs/ops/<package>/restore-runbook.md``.

One restore runbook per bundle (not per JTBD), aggregating every table
the bundle creates with the FK dependency order, the required
``pg_dump`` flags, the audit-chain re-verification step, and a
step-by-step disaster-recovery procedure.

Item 7 of :doc:`docs/improvements`, W2 of
:doc:`docs/v0.3.0-engineering-plan`. Sibling artefact to item 1's
``backend/migrations/safety/`` reports — both are operable-output
generators that lift bespoke per-project runbooks into deterministic,
byte-identical generation. Distinct from item 15 (admin console): the
admin console operates on a *running* system, this artefact operates on
*cold storage*.

The runbook lists the bundle's tables in topological FK-dependency
order. The bundle's tables don't have host-app FKs (each JTBD has its
own ``CREATE TABLE`` independent of the others), but every entity table
plus the per-JTBD ``<table>_idempotency_keys`` table (item 6) carries a
``tenant_id`` column that conceptually references the host's
``tenants`` table. Sequenced order is deterministic: entity tables
sorted by ``jtbd.id``, then any per-JTBD ``idempotency_keys`` tables
when item 6 lands. Item 6's idempotency tables are *gracefully
tolerated* — when the sibling worker-idempotency hasn't landed
``project.idempotency_ttl_hours``, the runbook still emits cleanly,
lists only entity tables, and notes the idempotency cohort as "(not
enabled in this bundle)".

The fixture-registry primer at :mod:`._fixture_registry` records the
attribute paths this generator reads; the bidirectional coverage test
(Pre-mortem Scenario 1 of :doc:`docs/v0.3.0-engineering-plan` §5)
cross-checks generator and registry.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].audit_topics",
	"jtbds[].id",
	"jtbds[].table_name",
	"jtbds[].title",
	"project.idempotency_ttl_hours",
	"project.name",
	"project.package",
	"project.tenancy",
)


def _idempotency_enabled(bundle: NormalizedBundle) -> bool:
	"""Detect whether item 6 (router-level idempotency keys) is wired.

	The sibling worker-idempotency lands ``project.idempotency_ttl_hours``
	on :class:`NormalizedProject` and emits per-JTBD
	``<table>_idempotency_keys`` migrations through ``db_migration``.
	If that field is missing on the bundle (older codepath, or sibling
	hasn't landed when this runbook regenerates), the runbook tolerates
	the absence and emits the entity-only table list.
	"""

	# ``getattr`` with a sentinel keeps the runbook regen-safe across
	# any reorder of W2 sub-batches; production paths always populate
	# the attribute (None when the bundle didn't opt into a custom TTL,
	# int when it did — either way, "enabled").
	return getattr(bundle.project, "idempotency_ttl_hours", "__missing__") != "__missing__"


def _table_view(bundle: NormalizedBundle) -> list[dict[str, object]]:
	"""Return the topo-sorted list of (table, kind, jtbd_id) rows.

	The bundle's tables are independent of each other (no inter-JTBD
	FKs are emitted by ``db_migration``), so the topological order is
	just a stable sort by JTBD id, with the per-JTBD idempotency table
	appearing *after* its owning entity table when item 6 is wired.
	"""

	enabled = _idempotency_enabled(bundle)
	rows: list[dict[str, object]] = []
	# Sort by jtbd id so the emission order is stable regardless of
	# bundle declaration order.
	for jt in sorted(bundle.jtbds, key=lambda j: j.id):
		rows.append(
			{
				"table": jt.table_name,
				"kind": "entity",
				"jtbd_id": jt.id,
				"jtbd_title": jt.title,
			}
		)
		if enabled:
			rows.append(
				{
					"table": f"{jt.table_name}_idempotency_keys",
					"kind": "idempotency",
					"jtbd_id": jt.id,
					"jtbd_title": jt.title,
				}
			)
	return rows


def _audit_topic_view(bundle: NormalizedBundle) -> list[str]:
	"""Return the deduplicated, sorted list of audit topics in the bundle."""

	# Bundle.all_audit_topics is already sorted+deduplicated by
	# normalize(). Defensive copy to a list so the template can iterate.
	return list(bundle.all_audit_topics)


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	"""Emit one ``docs/ops/<package>/restore-runbook.md`` per bundle.

	Per-bundle generator — one file regardless of how many JTBDs the
	bundle declares — per the engineering plan's principle 2 (per-bundle
	generators must be aggregations).
	"""

	tables = _table_view(bundle)
	topics = _audit_topic_view(bundle)
	idempotency_enabled = _idempotency_enabled(bundle)
	content = render(
		"restore_runbook.md.j2",
		project=bundle.project,
		bundle=bundle,
		tables=tables,
		audit_topics=topics,
		idempotency_enabled=idempotency_enabled,
		entity_count=sum(1 for t in tables if t["kind"] == "entity"),
	)
	return GeneratedFile(
		path=f"docs/ops/{bundle.project.package}/restore-runbook.md",
		content=content,
	)
