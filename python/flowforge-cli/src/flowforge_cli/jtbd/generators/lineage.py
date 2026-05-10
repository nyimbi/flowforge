"""Per-bundle generator: emit ``lineage.json`` at the bundle root.

Item 11 of :doc:`docs/improvements`, W3 of
:doc:`docs/v0.3.0-engineering-plan`. Sibling artefact to item 8's
``openapi.yaml`` and item 16's ``analytics.{py,ts}``: a static,
bundle-derived spec that downstream tooling (privacy review, GDPR /
HIPAA / CCPA audits, data-mapping inventories) can consume *without*
booting the generated app.

The graph traces every ``data_capture`` field across the five
generation-pipeline stages a host application moves the value through:

* ``form_input`` — the Step.tsx field rendered by ``frontend.py``.
* ``service_layer`` — the per-JTBD ``service.py`` fire entrypoint that
  receives the deserialised payload.
* ``orm_column`` — the SQLAlchemy column emitted by ``sa_model.py``
  (table + column + sa_type).
* ``audit_event_payload`` — the audit topics ``derive_audit_topics``
  attaches to the JTBD's transitions.
* ``outbox_envelope`` — the outbox ports the host wires through; carries
  the same audit topics + the JTBD's ``notifications`` channel/audience
  triples.

For PII fields (``pii: true`` *or* ``kind`` in ``SENSITIVE_FIELD_KINDS``)
the generator also emits:

* ``retention_window_years`` — default 7y when ``compliance`` includes
  ``HIPAA`` or ``SOX``, else 3y. Bundle-overridable via
  ``project.lineage.retention_years``.
* ``redaction_strategy`` — a dict keyed by the five stages naming the
  redaction recipe at each. Form input is ``visible``; ORM column is
  ``stored_as_is``; audit payload + outbox envelope are
  ``redacted_mask``; service layer is ``stored_as_is`` (the engine sees
  the raw value when validating + persisting).
* ``exposure_surfaces`` — list of ``{role, surface}`` pairs naming each
  read surface where the role can see the field, derived from the
  synthesised permissions catalog (``permissions.py``) the W0 generator
  emits. Surfaces today: ``service.read`` (FastAPI router GET), and
  ``admin_console.audit_viewer`` (item 15's tenant-scoped admin
  console's audit-log viewer).

The artifact is stable JSON: ``json.dumps(..., indent=2,
sort_keys=True)`` plus a trailing newline so two regens against the same
bundle produce byte-identical output (Principle 1 of the v0.3.0
engineering plan + W3 acceptance criteria).

The fixture-registry primer at :mod:`._fixture_registry` records the
attribute paths this generator reads; the bidirectional coverage test
(Pre-mortem Scenario 1 of :doc:`docs/v0.3.0-engineering-plan` §5)
cross-checks generator and registry.
"""

from __future__ import annotations

import json
from typing import Any

from ..normalize import NormalizedBundle, NormalizedField, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].audit_topics",
	"jtbds[].class_name",
	"jtbds[].compliance",
	"jtbds[].data_sensitivity",
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].kind",
	"jtbds[].fields[].label",
	"jtbds[].fields[].pii",
	"jtbds[].fields[].sa_type",
	"jtbds[].id",
	"jtbds[].module_name",
	"jtbds[].notifications",
	"jtbds[].permissions",
	"jtbds[].table_name",
	"jtbds[].title",
	"project.lineage.retention_years",
	"project.name",
	"project.package",
)


# Sensitive field kinds — task-defined PII set. ``text`` and ``textarea``
# are deliberately *not* in this set: they require an explicit ``pii``
# flag from the bundle author. Adding a kind here is taxonomy expansion
# and must be documented in :doc:`docs/improvements` item 11.
SENSITIVE_FIELD_KINDS: frozenset[str] = frozenset(
	{
		"email",
		"phone",
		"address",
		"signature",
		"file",
		"party_ref",
	}
)


# Compliance regimes that bump the default retention window from 3y to 7y.
# HIPAA: 6y for medical records — bumped to 7y to align with SOX. SOX: 7y
# for financial-controls audit trail. Future regimes (NIST-800-53,
# ISO27001) keep the 3y default unless their declared retention is longer.
_LONG_RETENTION_REGIMES: frozenset[str] = frozenset({"HIPAA", "SOX"})

_DEFAULT_RETENTION_YEARS_DEFAULT = 3
_DEFAULT_RETENTION_YEARS_LONG = 7


# Stage identifiers — kept as a tuple so emission order is stable
# regardless of dict iteration timing in the test layer.
_STAGES: tuple[str, ...] = (
	"form_input",
	"service_layer",
	"orm_column",
	"audit_event_payload",
	"outbox_envelope",
)


# Per-stage redaction strategy for a PII field. Non-PII fields omit the
# ``redaction_strategy`` block entirely so the JSON stays compact.
#
# * ``form_input``  — visible to the actor entering the value.
# * ``service_layer`` — engine fire entrypoint sees the raw value while
#   validating + persisting. Mirrors how the runtime actually works.
# * ``orm_column`` — stored as-is in the JTBD entity table; redaction is
#   a downstream concern (host adapters can encrypt-at-rest).
# * ``audit_event_payload`` — audit sinks see a masked variant; the
#   bundle's audit topics carry the *event*, not the field value.
# * ``outbox_envelope`` — outbox dispatch mirrors audit redaction so the
#   notification channels (email, slack) never re-leak the value.
_PII_REDACTION_STRATEGY: dict[str, str] = {
	"form_input": "visible",
	"service_layer": "stored_as_is",
	"orm_column": "stored_as_is",
	"audit_event_payload": "redacted_mask",
	"outbox_envelope": "redacted_mask",
}


def _is_pii(field: NormalizedField) -> bool:
	"""True when the field is PII per the W3 lineage rules.

	A field is PII when *either* the bundle author declared ``pii: true``
	*or* the field's ``kind`` is in :data:`SENSITIVE_FIELD_KINDS`. Both
	signals matter: ``pii: true`` lets authors opt a ``text`` field in;
	the kind-set covers fields where the author forgot but the runtime
	still leaks PII through the field's storage shape.
	"""

	assert isinstance(field, NormalizedField)
	return bool(field.pii) or field.kind in SENSITIVE_FIELD_KINDS


def _retention_years(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> int:
	"""Resolve the retention window in years for a JTBD's PII fields.

	Precedence (matches docstring):

	1. ``project.lineage.retention_years`` (explicit bundle override).
	2. 7y when the JTBD's ``compliance`` list intersects
	   :data:`_LONG_RETENTION_REGIMES` (HIPAA / SOX).
	3. 3y default.
	"""

	override = bundle.project.lineage_retention_years
	if override is not None:
		return int(override)
	if any(c in _LONG_RETENTION_REGIMES for c in jtbd.compliance):
		return _DEFAULT_RETENTION_YEARS_LONG
	return _DEFAULT_RETENTION_YEARS_DEFAULT


def _exposure_surfaces(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> list[dict[str, str]]:
	"""Return the sorted list of ``{role, surface}`` exposure pairs.

	Mirrors the synthesised permissions catalog in ``permissions.py``:
	every shared role currently inherits the full permission tuple, so
	each role appears against the read surfaces that PII fields surface
	through. Surfaces today:

	* ``service.read`` — service-layer GET endpoint emitted by
	  ``domain_service.py`` + ``domain_router.py``; gated by
	  ``<jtbd>.read``.
	* ``admin_console.audit_viewer`` — item 15's per-tenant admin console
	  audit-log viewer; reads from ``AuditSink``.

	Sorted by ``(role, surface)`` so the lineage JSON regenerates
	byte-identically across runs.
	"""

	# Roles authorised to read the JTBD's records. ``permissions.py``
	# gives every shared role the full permission set (the W0 catalog is
	# uniform), so include every shared role plus the JTBD's actor role
	# (which may or may not also be in ``shared_roles``). Deduplicated
	# via set membership so the output stays byte-stable regardless of
	# declaration order.
	roles: set[str] = set(bundle.shared_roles)
	if jtbd.actor_role:
		roles.add(jtbd.actor_role)
	# Surfaces: stable list, alphabetical for determinism.
	surfaces = ("admin_console.audit_viewer", "service.read")
	pairs: list[dict[str, str]] = []
	for role in sorted(roles):
		for surface in surfaces:
			pairs.append({"role": role, "surface": surface})
	return pairs


def _stage_records(
	bundle: NormalizedBundle,
	jtbd: NormalizedJTBD,
	field: NormalizedField,
	pii: bool,
) -> list[dict[str, Any]]:
	"""Build the per-stage trace records for one ``data_capture`` field.

	Each stage records ``stage`` plus a deterministic ``location``
	pointing at the generated file (frontend / backend / migration) the
	stage corresponds to. PII stages additionally carry the per-stage
	``redaction`` recipe so privacy reviewers can audit the masking
	contract end-to-end.
	"""

	pkg = bundle.project.package
	rows: list[dict[str, Any]] = []

	# 1. form_input — Step.tsx in the per-JTBD frontend tree.
	form_row: dict[str, Any] = {
		"stage": "form_input",
		"location": f"frontend/src/{pkg}/{jtbd.module_name}/Step.tsx",
		"form_field_id": field.id,
		"label": field.label,
	}
	if pii:
		form_row["redaction"] = _PII_REDACTION_STRATEGY["form_input"]
	rows.append(form_row)

	# 2. service_layer — domain_service.py per-JTBD module.
	svc_row: dict[str, Any] = {
		"stage": "service_layer",
		"location": f"backend/src/{pkg}/{jtbd.module_name}/service.py",
		"entrypoint": f"{jtbd.class_name}Service.fire",
	}
	if pii:
		svc_row["redaction"] = _PII_REDACTION_STRATEGY["service_layer"]
	rows.append(svc_row)

	# 3. orm_column — SQLAlchemy model + the underlying SQL column.
	orm_row: dict[str, Any] = {
		"stage": "orm_column",
		"location": f"backend/src/{pkg}/{jtbd.module_name}/models.py",
		"table": jtbd.table_name,
		"column": field.id,
		"sa_type": field.sa_type,
	}
	if pii:
		orm_row["redaction"] = _PII_REDACTION_STRATEGY["orm_column"]
	rows.append(orm_row)

	# 4. audit_event_payload — every audit topic the JTBD emits *can*
	# carry the field value through its payload. Topic list is the
	# already-sorted ``audit_topics`` tuple from ``derive_audit_topics``.
	audit_row: dict[str, Any] = {
		"stage": "audit_event_payload",
		"location": "audit_sink",
		"topics": list(jtbd.audit_topics),
	}
	if pii:
		audit_row["redaction"] = _PII_REDACTION_STRATEGY["audit_event_payload"]
	rows.append(audit_row)

	# 5. outbox_envelope — outbox dispatch mirrors audit topics + the
	# JTBD's notification channels/audiences. Sorted by
	# ``(channel, audience, trigger)`` for stable emission.
	notif_targets = sorted(
		[
			{
				"channel": n.channel,
				"audience": n.audience,
				"trigger": n.trigger,
			}
			for n in jtbd.notifications
		],
		key=lambda d: (d["channel"], d["audience"], d["trigger"]),
	)
	outbox_row: dict[str, Any] = {
		"stage": "outbox_envelope",
		"location": "outbox_registry",
		"topics": list(jtbd.audit_topics),
		"notification_targets": notif_targets,
	}
	if pii:
		outbox_row["redaction"] = _PII_REDACTION_STRATEGY["outbox_envelope"]
	rows.append(outbox_row)

	# Defensive ordering invariant: stages are emitted in the canonical
	# order so downstream graph consumers don't have to re-sort.
	assert tuple(r["stage"] for r in rows) == _STAGES, (
		"lineage stages must be emitted in canonical order"
	)
	return rows


def _field_record(
	bundle: NormalizedBundle,
	jtbd: NormalizedJTBD,
	field: NormalizedField,
) -> dict[str, Any]:
	"""Build one ``fields[]`` record for the lineage JSON."""

	pii = _is_pii(field)
	record: dict[str, Any] = {
		"id": field.id,
		"kind": field.kind,
		"label": field.label,
		"pii": pii,
		"stages": _stage_records(bundle, jtbd, field, pii),
	}
	if pii:
		record["retention_window_years"] = _retention_years(bundle, jtbd)
		record["redaction_strategy"] = dict(_PII_REDACTION_STRATEGY)
		record["exposure_surfaces"] = _exposure_surfaces(bundle, jtbd)
	return record


def _jtbd_record(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> dict[str, Any]:
	"""Build one ``jtbds[]`` record for the lineage JSON."""

	# Sort fields by id so the JSON regenerates byte-identically regardless
	# of bundle declaration order.
	fields = [
		_field_record(bundle, jtbd, f)
		for f in sorted(jtbd.fields, key=lambda x: x.id)
	]
	return {
		"id": jtbd.id,
		"title": jtbd.title,
		"compliance": list(jtbd.compliance),
		"data_sensitivity": list(jtbd.data_sensitivity),
		"pii_field_count": sum(1 for f in fields if f["pii"]),
		"field_count": len(fields),
		"fields": fields,
	}


def _build_graph(bundle: NormalizedBundle) -> dict[str, Any]:
	"""Assemble the bundle-level lineage graph document."""

	# Sort JTBDs by id so iteration order is stable.
	jtbds = [
		_jtbd_record(bundle, jt)
		for jt in sorted(bundle.jtbds, key=lambda j: j.id)
	]
	override = bundle.project.lineage_retention_years
	return {
		"schema_version": "1.0.0",
		"bundle": {
			"name": bundle.project.name,
			"package": bundle.project.package,
			"retention_years_override": override,
		},
		"stages": list(_STAGES),
		"sensitive_field_kinds": sorted(SENSITIVE_FIELD_KINDS),
		"jtbds": jtbds,
	}


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	"""Emit one ``lineage.json`` per bundle.

	Per-bundle generator — one file regardless of how many JTBDs the
	bundle declares — per the engineering plan's principle 2 (per-bundle
	generators must be aggregations).
	"""

	graph = _build_graph(bundle)
	# ``sort_keys=True`` is the determinism contract; trailing newline
	# matches the form_spec / openapi convention so POSIX tooling
	# (diff, grep) sees a complete file.
	content = json.dumps(graph, indent=2, sort_keys=True) + "\n"
	return GeneratedFile(path="lineage.json", content=content)
