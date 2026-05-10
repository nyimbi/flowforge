"""``flowforge bundle-diff`` — deploy-safety diff between two JTBD bundles.

Item 10 of :doc:`docs/improvements`, W3 of
:doc:`docs/v0.3.0-engineering-plan`.

Mechanical comparison of two parsed JTBD bundles, categorising each
change into one of three deploy-safety classes:

* ``additive`` — new JTBDs, new optional fields, new info-level audit
  topics, new notifications, etc. Safe to ship without coordination.
* ``requires-coordination`` — new permissions, new required fields,
  renamed states, new approvals. Needs RBAC seed update + form
  invalidation + comms.
* ``breaking`` — removed JTBDs, removed fields, narrowed column types,
  enum values removed, transitions retargeted. Needs migration plan +
  instance-class compatibility check.

Outputs (any combination, all optional — text mode is the default):

* ``--json <path>`` — deterministic machine-readable report.
* ``--html <path>`` — single-file standalone HTML report (minimal JS
  for the expand/collapse affordance only).

Exit codes:

* ``0`` — diff produced; only additive findings.
* ``1`` — diff produced; ≥1 ``requires-coordination`` or ``breaking``
  finding. Use ``--exit-zero`` to suppress the non-zero exit.
* ``2`` — usage error / invalid input.

This is an *operational tool*: it does not emit files into
``examples/`` and is not part of the deterministic regen pipeline. The
categorisation rules are mechanical given two parsed bundles, so two
runs against the same input pair yield byte-identical reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from html import escape as _html_escape
from pathlib import Path
from typing import Annotated, Any

import typer


# ---------------------------------------------------------------------------
# Public model
# ---------------------------------------------------------------------------


class ChangeKind(str, Enum):
	"""Deploy-safety class for a single change."""

	ADDITIVE = "additive"
	REQUIRES_COORDINATION = "requires-coordination"
	BREAKING = "breaking"


_KIND_RANK: dict[ChangeKind, int] = {
	ChangeKind.BREAKING: 0,
	ChangeKind.REQUIRES_COORDINATION: 1,
	ChangeKind.ADDITIVE: 2,
}


@dataclass(frozen=True)
class Change:
	"""A single categorised diff entry.

	The triple ``(kind, path, category)`` is unique within a report.
	``path`` uses dotted JSON-ish notation: e.g.
	``jtbds[claim_intake].data_capture[email].kind``.
	"""

	kind: ChangeKind
	category: str
	path: str
	message: str
	old: Any | None = None
	new: Any | None = None

	def to_json(self) -> dict[str, Any]:
		return {
			"kind": self.kind.value,
			"category": self.category,
			"path": self.path,
			"message": self.message,
			"old": _jsonify(self.old),
			"new": _jsonify(self.new),
		}


@dataclass
class DiffReport:
	"""Aggregate diff result across two bundles."""

	old_label: str = "old"
	new_label: str = "new"
	changes: list[Change] = field(default_factory=list)

	def by_kind(self, kind: ChangeKind) -> list[Change]:
		return [c for c in self.changes if c.kind == kind]

	def counts(self) -> dict[str, int]:
		out: dict[str, int] = {k.value: 0 for k in ChangeKind}
		for c in self.changes:
			out[c.kind.value] += 1
		return out

	def has_blocking(self) -> bool:
		"""Return True iff any change is non-additive."""

		return any(c.kind != ChangeKind.ADDITIVE for c in self.changes)

	def sorted(self) -> list[Change]:
		"""Stable sort: kind (most-severe first) → path → category."""

		return sorted(
			self.changes,
			key=lambda c: (_KIND_RANK[c.kind], c.path, c.category),
		)


# ---------------------------------------------------------------------------
# Diff entry-point
# ---------------------------------------------------------------------------


def compute_diff(
	old: dict[str, Any],
	new: dict[str, Any],
	*,
	old_label: str = "old",
	new_label: str = "new",
) -> DiffReport:
	"""Categorise the differences between two parsed JTBD bundles."""

	assert isinstance(old, dict), "old bundle must be a dict"
	assert isinstance(new, dict), "new bundle must be a dict"

	report = DiffReport(old_label=old_label, new_label=new_label)
	_diff_project(old.get("project") or {}, new.get("project") or {}, report)
	_diff_shared(old.get("shared") or {}, new.get("shared") or {}, report)
	_diff_jtbds(old.get("jtbds") or [], new.get("jtbds") or [], report)
	report.changes = report.sorted()
	return report


# ---------------------------------------------------------------------------
# project.* rules
# ---------------------------------------------------------------------------


def _diff_project(old: dict[str, Any], new: dict[str, Any], report: DiffReport) -> None:
	# Renames at project level (name / package / domain / tenancy) almost
	# always require coordination — package rename retargets every emitted
	# table prefix; tenancy widening (single → multi) retargets every RLS
	# policy.
	for key in ("name", "package", "domain", "tenancy", "frontend_framework"):
		o, n = old.get(key), new.get(key)
		if o == n:
			continue
		# tenancy single → none is a contraction; package rename means a
		# fresh schema. Both are operational coordination items at minimum,
		# breaking if rows already exist.
		kind = ChangeKind.BREAKING if key in ("package", "tenancy") else ChangeKind.REQUIRES_COORDINATION
		report.changes.append(
			Change(
				kind=kind,
				category=f"project_{key}_changed",
				path=f"project.{key}",
				message=f"project.{key} changed: {o!r} → {n!r}",
				old=o,
				new=n,
			)
		)

	# Languages and currencies behave like flat sets — additions are
	# ADDITIVE, removals are REQUIRES_COORDINATION (translations may be
	# referenced by hosts; pulling a currency from circulation needs ops
	# acknowledgement but isn't a hard schema break).
	for key in ("languages", "currencies"):
		_diff_string_set(
			old.get(key) or [],
			new.get(key) or [],
			path=f"project.{key}",
			added_kind=ChangeKind.ADDITIVE,
			removed_kind=ChangeKind.REQUIRES_COORDINATION,
			added_category=f"project_{key}_added",
			removed_category=f"project_{key}_removed",
			report=report,
		)

	# project.frontend.form_renderer flag flip — additive when going
	# skeleton → real (capability gain); requires-coordination when
	# regressing real → skeleton (UI loses a feature).
	old_fr = (old.get("frontend") or {}).get("form_renderer")
	new_fr = (new.get("frontend") or {}).get("form_renderer")
	if old_fr != new_fr:
		if old_fr in (None, "skeleton") and new_fr == "real":
			kind = ChangeKind.ADDITIVE
			category = "form_renderer_upgraded"
			msg = f"form_renderer upgraded: {old_fr!r} → {new_fr!r}"
		else:
			kind = ChangeKind.REQUIRES_COORDINATION
			category = "form_renderer_changed"
			msg = f"form_renderer changed: {old_fr!r} → {new_fr!r}"
		report.changes.append(
			Change(
				kind=kind,
				category=category,
				path="project.frontend.form_renderer",
				message=msg,
				old=old_fr,
				new=new_fr,
			)
		)


# ---------------------------------------------------------------------------
# shared.* rules
# ---------------------------------------------------------------------------


def _diff_shared(old: dict[str, Any], new: dict[str, Any], report: DiffReport) -> None:
	# Shared roles — adding a role requires-coordination (RBAC seed must
	# learn it); removing a role is breaking (instances may reference it).
	_diff_string_set(
		old.get("roles") or [],
		new.get("roles") or [],
		path="shared.roles",
		added_kind=ChangeKind.REQUIRES_COORDINATION,
		removed_kind=ChangeKind.BREAKING,
		added_category="shared_role_added",
		removed_category="shared_role_removed",
		report=report,
	)

	# Shared permissions — same shape: add = coord, remove = breaking.
	_diff_string_set(
		old.get("permissions") or [],
		new.get("permissions") or [],
		path="shared.permissions",
		added_kind=ChangeKind.REQUIRES_COORDINATION,
		removed_kind=ChangeKind.BREAKING,
		added_category="shared_permission_added",
		removed_category="shared_permission_removed",
		report=report,
	)


def _diff_string_set(
	old_items: list[Any],
	new_items: list[Any],
	*,
	path: str,
	added_kind: ChangeKind,
	removed_kind: ChangeKind,
	added_category: str,
	removed_category: str,
	report: DiffReport,
) -> None:
	old_set = {x for x in old_items if isinstance(x, str)}
	new_set = {x for x in new_items if isinstance(x, str)}
	for item in sorted(new_set - old_set):
		report.changes.append(
			Change(
				kind=added_kind,
				category=added_category,
				path=f"{path}[{item}]",
				message=f"{path}: added {item!r}",
				new=item,
			)
		)
	for item in sorted(old_set - new_set):
		report.changes.append(
			Change(
				kind=removed_kind,
				category=removed_category,
				path=f"{path}[{item}]",
				message=f"{path}: removed {item!r}",
				old=item,
			)
		)


# ---------------------------------------------------------------------------
# jtbds[*] rules
# ---------------------------------------------------------------------------


def _index_by_id(items: list[Any]) -> dict[str, dict[str, Any]]:
	"""Index a list of dicts by their ``id`` key. Skip missing ids."""

	out: dict[str, dict[str, Any]] = {}
	for x in items:
		if not isinstance(x, dict):
			continue
		key = x.get("id")
		if isinstance(key, str) and key:
			out[key] = x
	return out


def _diff_jtbds(
	old_jtbds: list[Any],
	new_jtbds: list[Any],
	report: DiffReport,
) -> None:
	old_idx = _index_by_id(old_jtbds)
	new_idx = _index_by_id(new_jtbds)
	old_ids = set(old_idx)
	new_ids = set(new_idx)

	for jtbd_id in sorted(new_ids - old_ids):
		report.changes.append(
			Change(
				kind=ChangeKind.ADDITIVE,
				category="jtbd_added",
				path=f"jtbds[{jtbd_id}]",
				message=f"new JTBD {jtbd_id!r} added",
				new={"id": jtbd_id, "title": new_idx[jtbd_id].get("title")},
			)
		)

	for jtbd_id in sorted(old_ids - new_ids):
		report.changes.append(
			Change(
				kind=ChangeKind.BREAKING,
				category="jtbd_removed",
				path=f"jtbds[{jtbd_id}]",
				message=(
					f"JTBD {jtbd_id!r} removed — existing instances become "
					"orphaned and require a migration plan"
				),
				old={"id": jtbd_id, "title": old_idx[jtbd_id].get("title")},
			)
		)

	for jtbd_id in sorted(old_ids & new_ids):
		_diff_one_jtbd(old_idx[jtbd_id], new_idx[jtbd_id], report)


def _diff_one_jtbd(
	old: dict[str, Any],
	new: dict[str, Any],
	report: DiffReport,
) -> None:
	jtbd_id = old.get("id") or new.get("id") or "?"
	prefix = f"jtbds[{jtbd_id}]"

	# actor.role rename — actor.external flip can affect public exposure.
	_diff_actor(old.get("actor") or {}, new.get("actor") or {}, prefix, report)

	# data_capture[*] — by far the densest class.
	_diff_data_capture(
		old.get("data_capture") or [],
		new.get("data_capture") or [],
		prefix,
		report,
	)

	# edge_cases[*] — branch retarget = breaking; new edge = additive.
	_diff_edge_cases(
		old.get("edge_cases") or [],
		new.get("edge_cases") or [],
		prefix,
		report,
	)

	# approvals[*] — adding/removing reviewers is a coordination concern.
	_diff_approvals(
		old.get("approvals") or [],
		new.get("approvals") or [],
		prefix,
		report,
	)

	# notifications[*] — adding is additive; removing is also additive
	# because the worst-case is a missed notification, not a deploy block.
	_diff_notifications(
		old.get("notifications") or [],
		new.get("notifications") or [],
		prefix,
		report,
	)

	# documents_required[*] — adding a required doc kind is a coordination
	# concern (existing instances may not have it); removing a doc kind is
	# additive.
	_diff_documents_required(
		old.get("documents_required") or [],
		new.get("documents_required") or [],
		prefix,
		report,
	)

	# sla.breach_seconds tightening = coord; relaxation = additive.
	_diff_sla(old.get("sla") or {}, new.get("sla") or {}, prefix, report)

	# success_criteria, metrics — flat string sets, additive both ways.
	_diff_string_set(
		old.get("success_criteria") or [],
		new.get("success_criteria") or [],
		path=f"{prefix}.success_criteria",
		added_kind=ChangeKind.ADDITIVE,
		removed_kind=ChangeKind.ADDITIVE,
		added_category="success_criteria_added",
		removed_category="success_criteria_removed",
		report=report,
	)
	_diff_string_set(
		old.get("metrics") or [],
		new.get("metrics") or [],
		path=f"{prefix}.metrics",
		added_kind=ChangeKind.ADDITIVE,
		removed_kind=ChangeKind.ADDITIVE,
		added_category="metric_added",
		removed_category="metric_removed",
		report=report,
	)


def _diff_actor(
	old: dict[str, Any],
	new: dict[str, Any],
	prefix: str,
	report: DiffReport,
) -> None:
	old_role = old.get("role")
	new_role = new.get("role")
	if old_role != new_role and (old_role or new_role):
		report.changes.append(
			Change(
				kind=ChangeKind.REQUIRES_COORDINATION,
				category="actor_role_changed",
				path=f"{prefix}.actor.role",
				message=f"actor role changed: {old_role!r} → {new_role!r}",
				old=old_role,
				new=new_role,
			)
		)
	old_ext = bool(old.get("external", False))
	new_ext = bool(new.get("external", False))
	if old_ext != new_ext:
		# external=True → False shrinks the exposure surface (additive);
		# False → True widens it (coordination).
		kind = ChangeKind.ADDITIVE if old_ext and not new_ext else ChangeKind.REQUIRES_COORDINATION
		report.changes.append(
			Change(
				kind=kind,
				category="actor_external_changed",
				path=f"{prefix}.actor.external",
				message=f"actor.external changed: {old_ext} → {new_ext}",
				old=old_ext,
				new=new_ext,
			)
		)


# ---------------------------------------------------------------------------
# data_capture[*] — fields
# ---------------------------------------------------------------------------


# Maps a field ``kind`` to a numeric width-class so we can detect a
# narrowing change (e.g. ``textarea`` → ``text`` is a narrowing because
# the existing payload may not fit the narrower bound).
_KIND_WIDTH: dict[str, int] = {
	"textarea": 100,
	"text": 50,
	"address": 50,
	"signature": 40,
	"file": 40,
	"document_ref": 30,
	"party_ref": 30,
	"email": 30,
	"phone": 30,
	"datetime": 20,
	"date": 18,
	"money": 16,
	"number": 14,
	"enum": 10,
	"boolean": 8,
}


def _diff_data_capture(
	old_fields: list[Any],
	new_fields: list[Any],
	prefix: str,
	report: DiffReport,
) -> None:
	old_idx = _index_by_id(old_fields)
	new_idx = _index_by_id(new_fields)

	for fid in sorted(set(new_idx) - set(old_idx)):
		fnew = new_idx[fid]
		required = bool(fnew.get("required", False))
		if required:
			report.changes.append(
				Change(
					kind=ChangeKind.REQUIRES_COORDINATION,
					category="required_field_added",
					path=f"{prefix}.data_capture[{fid}]",
					message=(
						f"new required field {fid!r} (kind={fnew.get('kind')!r}) — "
						"forms must be re-issued; existing instances need backfill"
					),
					new=fnew,
				)
			)
		else:
			report.changes.append(
				Change(
					kind=ChangeKind.ADDITIVE,
					category="optional_field_added",
					path=f"{prefix}.data_capture[{fid}]",
					message=f"new optional field {fid!r} (kind={fnew.get('kind')!r})",
					new=fnew,
				)
			)

	for fid in sorted(set(old_idx) - set(new_idx)):
		report.changes.append(
			Change(
				kind=ChangeKind.BREAKING,
				category="field_removed",
				path=f"{prefix}.data_capture[{fid}]",
				message=(
					f"data_capture field {fid!r} removed — existing rows hold "
					"data that becomes unreachable; needs migration plan"
				),
				old=old_idx[fid],
			)
		)

	for fid in sorted(set(old_idx) & set(new_idx)):
		_diff_one_field(old_idx[fid], new_idx[fid], prefix, fid, report)


def _diff_one_field(
	old: dict[str, Any],
	new: dict[str, Any],
	prefix: str,
	fid: str,
	report: DiffReport,
) -> None:
	path = f"{prefix}.data_capture[{fid}]"

	# kind change — narrowing is breaking, widening is requires-coord
	# (data fits but UI/serialiser shape changes).
	old_kind = old.get("kind")
	new_kind = new.get("kind")
	if old_kind != new_kind:
		old_w = _KIND_WIDTH.get(old_kind or "", 0)
		new_w = _KIND_WIDTH.get(new_kind or "", 0)
		if old_kind and new_kind and new_w < old_w:
			report.changes.append(
				Change(
					kind=ChangeKind.BREAKING,
					category="field_kind_narrowed",
					path=f"{path}.kind",
					message=(
						f"field {fid!r} kind narrowed: {old_kind!r} → {new_kind!r} "
						"— existing rows may not fit the narrower type"
					),
					old=old_kind,
					new=new_kind,
				)
			)
		else:
			report.changes.append(
				Change(
					kind=ChangeKind.REQUIRES_COORDINATION,
					category="field_kind_changed",
					path=f"{path}.kind",
					message=f"field {fid!r} kind changed: {old_kind!r} → {new_kind!r}",
					old=old_kind,
					new=new_kind,
				)
			)

	# required flip
	old_req = bool(old.get("required", False))
	new_req = bool(new.get("required", False))
	if old_req != new_req:
		if not old_req and new_req:
			report.changes.append(
				Change(
					kind=ChangeKind.REQUIRES_COORDINATION,
					category="field_required_tightened",
					path=f"{path}.required",
					message=(
						f"field {fid!r} flipped optional → required — forms must "
						"invalidate; existing instances need backfill"
					),
					old=False,
					new=True,
				)
			)
		else:
			report.changes.append(
				Change(
					kind=ChangeKind.ADDITIVE,
					category="field_required_relaxed",
					path=f"{path}.required",
					message=f"field {fid!r} flipped required → optional",
					old=True,
					new=False,
				)
			)

	# pii flag — promoting to PII is a coordination concern (audit
	# pipelines, retention rules); demoting is additive.
	old_pii = bool(old.get("pii", False))
	new_pii = bool(new.get("pii", False))
	if old_pii != new_pii:
		if new_pii and not old_pii:
			report.changes.append(
				Change(
					kind=ChangeKind.REQUIRES_COORDINATION,
					category="field_pii_promoted",
					path=f"{path}.pii",
					message=(
						f"field {fid!r} promoted to PII — retention/audit "
						"pipeline must reclassify"
					),
					old=False,
					new=True,
				)
			)
		else:
			report.changes.append(
				Change(
					kind=ChangeKind.ADDITIVE,
					category="field_pii_demoted",
					path=f"{path}.pii",
					message=f"field {fid!r} demoted from PII",
					old=True,
					new=False,
				)
			)

	# validation.enum value removal = breaking.
	_diff_field_validation(old, new, path, fid, report)

	# label rename → coordination (analytics dashboards, screenshots).
	old_label = old.get("label")
	new_label = new.get("label")
	if old_label != new_label and (old_label or new_label):
		report.changes.append(
			Change(
				kind=ChangeKind.REQUIRES_COORDINATION,
				category="field_label_changed",
				path=f"{path}.label",
				message=f"field {fid!r} label changed: {old_label!r} → {new_label!r}",
				old=old_label,
				new=new_label,
			)
		)


def _diff_field_validation(
	old: dict[str, Any],
	new: dict[str, Any],
	path: str,
	fid: str,
	report: DiffReport,
) -> None:
	old_v = old.get("validation") or {}
	new_v = new.get("validation") or {}

	# Enum value set narrowing.
	old_enum = old_v.get("enum") if isinstance(old_v.get("enum"), list) else None
	new_enum = new_v.get("enum") if isinstance(new_v.get("enum"), list) else None
	if isinstance(old_enum, list) and isinstance(new_enum, list):
		removed = sorted(
			str(x) for x in set(map(str, old_enum)) - set(map(str, new_enum))
		)
		for val in removed:
			report.changes.append(
				Change(
					kind=ChangeKind.BREAKING,
					category="enum_value_removed",
					path=f"{path}.validation.enum[{val}]",
					message=(
						f"field {fid!r} dropped enum value {val!r} — existing "
						"rows holding this value become invalid"
					),
					old=val,
				)
			)
		added = sorted(
			str(x) for x in set(map(str, new_enum)) - set(map(str, old_enum))
		)
		for val in added:
			report.changes.append(
				Change(
					kind=ChangeKind.ADDITIVE,
					category="enum_value_added",
					path=f"{path}.validation.enum[{val}]",
					message=f"field {fid!r} added enum value {val!r}",
					new=val,
				)
			)

	# Length / range tightening — comparable numeric bounds.
	for bound, op in (("max_length", min), ("max", min), ("min", max)):
		o = old_v.get(bound)
		n = new_v.get(bound)
		if isinstance(o, (int, float)) and isinstance(n, (int, float)) and o != n:
			tightened = (op(o, n) == n) if op is min else (op(o, n) == n)
			if tightened:
				report.changes.append(
					Change(
						kind=ChangeKind.BREAKING,
						category=f"field_validation_{bound}_tightened",
						path=f"{path}.validation.{bound}",
						message=(
							f"field {fid!r} validation.{bound} tightened: "
							f"{o} → {n} — existing rows may violate the new bound"
						),
						old=o,
						new=n,
					)
				)
			else:
				report.changes.append(
					Change(
						kind=ChangeKind.ADDITIVE,
						category=f"field_validation_{bound}_relaxed",
						path=f"{path}.validation.{bound}",
						message=f"field {fid!r} validation.{bound} relaxed: {o} → {n}",
						old=o,
						new=n,
					)
				)


# ---------------------------------------------------------------------------
# edge_cases[*]
# ---------------------------------------------------------------------------


def _diff_edge_cases(
	old_cases: list[Any],
	new_cases: list[Any],
	prefix: str,
	report: DiffReport,
) -> None:
	old_idx = _index_by_id(old_cases)
	new_idx = _index_by_id(new_cases)

	for eid in sorted(set(new_idx) - set(old_idx)):
		report.changes.append(
			Change(
				kind=ChangeKind.ADDITIVE,
				category="edge_case_added",
				path=f"{prefix}.edge_cases[{eid}]",
				message=(
					f"new edge_case {eid!r} (handle="
					f"{new_idx[eid].get('handle')!r})"
				),
				new=new_idx[eid],
			)
		)

	for eid in sorted(set(old_idx) - set(new_idx)):
		report.changes.append(
			Change(
				kind=ChangeKind.BREAKING,
				category="edge_case_removed",
				path=f"{prefix}.edge_cases[{eid}]",
				message=(
					f"edge_case {eid!r} removed — instances currently parked "
					"on the resulting state need a retarget plan"
				),
				old=old_idx[eid],
			)
		)

	for eid in sorted(set(old_idx) & set(new_idx)):
		_diff_one_edge_case(old_idx[eid], new_idx[eid], prefix, eid, report)


def _diff_one_edge_case(
	old: dict[str, Any],
	new: dict[str, Any],
	prefix: str,
	eid: str,
	report: DiffReport,
) -> None:
	path = f"{prefix}.edge_cases[{eid}]"

	old_handle = old.get("handle")
	new_handle = new.get("handle")
	if old_handle != new_handle:
		# Handle change always implies a transition retarget — breaking.
		report.changes.append(
			Change(
				kind=ChangeKind.BREAKING,
				category="edge_case_handle_changed",
				path=f"{path}.handle",
				message=(
					f"edge_case {eid!r} handle changed: {old_handle!r} → "
					f"{new_handle!r} — transition retargeted; existing "
					"instances on the prior state must migrate"
				),
				old=old_handle,
				new=new_handle,
			)
		)

	old_branch = old.get("branch_to")
	new_branch = new.get("branch_to")
	if old_branch != new_branch and (old_branch or new_branch):
		# Branch retarget is the canonical "transition with existing
		# instances retargeted" example from the plan.
		report.changes.append(
			Change(
				kind=ChangeKind.BREAKING,
				category="edge_case_branch_retargeted",
				path=f"{path}.branch_to",
				message=(
					f"edge_case {eid!r} branch_to retargeted: "
					f"{old_branch!r} → {new_branch!r} — instances on the "
					"prior target state need a migration plan"
				),
				old=old_branch,
				new=new_branch,
			)
		)

	old_cond = old.get("condition")
	new_cond = new.get("condition")
	if old_cond != new_cond and (old_cond or new_cond):
		# Condition tweak doesn't retarget but it changes which
		# instances trip the edge — coord-class.
		report.changes.append(
			Change(
				kind=ChangeKind.REQUIRES_COORDINATION,
				category="edge_case_condition_changed",
				path=f"{path}.condition",
				message=(
					f"edge_case {eid!r} condition changed: "
					f"{old_cond!r} → {new_cond!r}"
				),
				old=old_cond,
				new=new_cond,
			)
		)


# ---------------------------------------------------------------------------
# approvals[*]
# ---------------------------------------------------------------------------


def _approval_key(a: dict[str, Any]) -> str:
	"""Stable key for an approval entry: ``<role>:<policy>``."""

	return f"{a.get('role', '?')}:{a.get('policy', '?')}"


def _diff_approvals(
	old_apps: list[Any],
	new_apps: list[Any],
	prefix: str,
	report: DiffReport,
) -> None:
	old_keys = {
		_approval_key(a): a for a in old_apps if isinstance(a, dict)
	}
	new_keys = {
		_approval_key(a): a for a in new_apps if isinstance(a, dict)
	}
	for key in sorted(set(new_keys) - set(old_keys)):
		report.changes.append(
			Change(
				kind=ChangeKind.REQUIRES_COORDINATION,
				category="approval_added",
				path=f"{prefix}.approvals[{key}]",
				message=(
					f"new approval gate {key!r} — RBAC seed and approver "
					"roster need updating before deploy"
				),
				new=new_keys[key],
			)
		)
	for key in sorted(set(old_keys) - set(new_keys)):
		report.changes.append(
			Change(
				kind=ChangeKind.REQUIRES_COORDINATION,
				category="approval_removed",
				path=f"{prefix}.approvals[{key}]",
				message=(
					f"approval gate {key!r} removed — instances awaiting "
					"this approval auto-clear; comms required"
				),
				old=old_keys[key],
			)
		)


# ---------------------------------------------------------------------------
# notifications[*]
# ---------------------------------------------------------------------------


def _notif_key(n: dict[str, Any]) -> str:
	return f"{n.get('trigger', '?')}:{n.get('channel', '?')}:{n.get('audience', '?')}"


def _diff_notifications(
	old_notifs: list[Any],
	new_notifs: list[Any],
	prefix: str,
	report: DiffReport,
) -> None:
	old_keys = {
		_notif_key(n): n for n in old_notifs if isinstance(n, dict)
	}
	new_keys = {
		_notif_key(n): n for n in new_notifs if isinstance(n, dict)
	}
	for key in sorted(set(new_keys) - set(old_keys)):
		report.changes.append(
			Change(
				kind=ChangeKind.ADDITIVE,
				category="notification_added",
				path=f"{prefix}.notifications[{key}]",
				message=f"new notification {key!r}",
				new=new_keys[key],
			)
		)
	for key in sorted(set(old_keys) - set(new_keys)):
		report.changes.append(
			Change(
				kind=ChangeKind.ADDITIVE,
				category="notification_removed",
				path=f"{prefix}.notifications[{key}]",
				message=f"notification {key!r} removed",
				old=old_keys[key],
			)
		)


# ---------------------------------------------------------------------------
# documents_required[*]
# ---------------------------------------------------------------------------


def _doc_key(d: dict[str, Any]) -> str:
	return str(d.get("kind", "?"))


def _diff_documents_required(
	old_docs: list[Any],
	new_docs: list[Any],
	prefix: str,
	report: DiffReport,
) -> None:
	old_idx = {
		_doc_key(d): d for d in old_docs if isinstance(d, dict)
	}
	new_idx = {
		_doc_key(d): d for d in new_docs if isinstance(d, dict)
	}
	for key in sorted(set(new_idx) - set(old_idx)):
		new_doc = new_idx[key]
		min_count = int(new_doc.get("min", 1) or 0)
		if min_count >= 1:
			report.changes.append(
				Change(
					kind=ChangeKind.REQUIRES_COORDINATION,
					category="required_document_added",
					path=f"{prefix}.documents_required[{key}]",
					message=(
						f"new required document {key!r} (min={min_count}) — "
						"existing instances must upload before they can advance"
					),
					new=new_doc,
				)
			)
		else:
			report.changes.append(
				Change(
					kind=ChangeKind.ADDITIVE,
					category="optional_document_added",
					path=f"{prefix}.documents_required[{key}]",
					message=f"new optional document {key!r}",
					new=new_doc,
				)
			)
	for key in sorted(set(old_idx) - set(new_idx)):
		report.changes.append(
			Change(
				kind=ChangeKind.ADDITIVE,
				category="document_removed",
				path=f"{prefix}.documents_required[{key}]",
				message=f"document kind {key!r} removed",
				old=old_idx[key],
			)
		)


# ---------------------------------------------------------------------------
# sla.*
# ---------------------------------------------------------------------------


def _diff_sla(
	old: dict[str, Any],
	new: dict[str, Any],
	prefix: str,
	report: DiffReport,
) -> None:
	o = old.get("breach_seconds")
	n = new.get("breach_seconds")
	if isinstance(o, (int, float)) and isinstance(n, (int, float)) and o != n:
		if n < o:
			report.changes.append(
				Change(
					kind=ChangeKind.REQUIRES_COORDINATION,
					category="sla_tightened",
					path=f"{prefix}.sla.breach_seconds",
					message=(
						f"SLA breach window tightened: {o}s → {n}s — alerts "
						"will fire sooner; on-call rotation should review"
					),
					old=o,
					new=n,
				)
			)
		else:
			report.changes.append(
				Change(
					kind=ChangeKind.ADDITIVE,
					category="sla_relaxed",
					path=f"{prefix}.sla.breach_seconds",
					message=f"SLA breach window relaxed: {o}s → {n}s",
					old=o,
					new=n,
				)
			)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _jsonify(value: Any) -> Any:
	"""Coerce arbitrary parsed-bundle values into JSON-safe primitives."""

	if value is None or isinstance(value, (bool, int, float, str)):
		return value
	if isinstance(value, dict):
		return {str(k): _jsonify(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
	if isinstance(value, (list, tuple)):
		return [_jsonify(v) for v in value]
	return str(value)


def render_json(report: DiffReport) -> str:
	"""Render the report as deterministic JSON."""

	payload = {
		"old": report.old_label,
		"new": report.new_label,
		"counts": report.counts(),
		"has_blocking": report.has_blocking(),
		"changes": [c.to_json() for c in report.sorted()],
	}
	return json.dumps(payload, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# HTML rendering — single-file, minimal JS
# ---------------------------------------------------------------------------


# Kept inline so the report is a self-contained `.html` file. The JS
# is only what's needed for the kind-filter chips and the per-row
# expand-collapse — no frameworks, no fetches, no external CSS.
_HTML_CSS = """
* { box-sizing: border-box; }
body { font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; color: #1a1d23; background: #f6f7f9; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7280; margin: 24px 0 8px; }
.meta { color: #6b7280; margin-bottom: 16px; }
.summary { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.chip { padding: 6px 12px; border-radius: 999px; font-weight: 600; cursor: pointer; user-select: none; border: 1px solid transparent; }
.chip[data-active="false"] { opacity: 0.4; }
.chip.breaking { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
.chip.requires-coordination { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
.chip.additive { background: #d1fae5; color: #065f46; border-color: #6ee7b7; }
.chip.total { background: #e5e7eb; color: #374151; border-color: #d1d5db; }
table { border-collapse: collapse; width: 100%; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
th { background: #f9fafb; font-size: 12px; text-transform: uppercase; letter-spacing: 0.4px; color: #6b7280; }
tr.breaking td.kind { color: #991b1b; font-weight: 600; }
tr.requires-coordination td.kind { color: #92400e; font-weight: 600; }
tr.additive td.kind { color: #065f46; font-weight: 600; }
tr.hidden { display: none; }
code, .path { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12px; color: #374151; word-break: break-all; }
.row-detail { background: #f9fafb; }
.row-detail pre { margin: 0; font-size: 11px; white-space: pre-wrap; word-break: break-all; }
.expand-btn { cursor: pointer; user-select: none; color: #6b7280; font-family: ui-monospace, monospace; }
.empty { padding: 24px; text-align: center; color: #6b7280; }
"""

# Tiny JS: filter rows by the kind chip and toggle per-row JSON detail.
_HTML_JS = """
(function(){
	var chips = document.querySelectorAll('.chip[data-kind]');
	var rows = document.querySelectorAll('tr[data-kind]');
	var active = { 'breaking': true, 'requires-coordination': true, 'additive': true };
	function render() {
		rows.forEach(function(r){
			var k = r.getAttribute('data-kind');
			r.classList.toggle('hidden', !active[k]);
			var d = document.getElementById('detail-' + r.getAttribute('data-id'));
			if (d) d.classList.toggle('hidden', !active[k] || d.getAttribute('data-open') !== '1');
		});
		chips.forEach(function(c){
			var k = c.getAttribute('data-kind');
			c.setAttribute('data-active', active[k] ? 'true' : 'false');
		});
	}
	chips.forEach(function(c){
		c.addEventListener('click', function(){
			var k = c.getAttribute('data-kind');
			active[k] = !active[k];
			render();
		});
	});
	document.querySelectorAll('.expand-btn').forEach(function(b){
		b.addEventListener('click', function(){
			var id = b.getAttribute('data-target');
			var d = document.getElementById(id);
			if (!d) return;
			var open = d.getAttribute('data-open') === '1';
			d.setAttribute('data-open', open ? '0' : '1');
			d.classList.toggle('hidden', open);
			b.textContent = open ? '▸' : '▾';
		});
	});
	render();
})();
"""


def render_html(report: DiffReport) -> str:
	"""Render the report as a self-contained HTML page."""

	counts = report.counts()
	rows: list[str] = []
	# Stable, deterministic id per row: the index in the sorted list.
	for idx, c in enumerate(report.sorted()):
		row_id = f"row-{idx}"
		detail_payload = json.dumps(
			{"old": _jsonify(c.old), "new": _jsonify(c.new)},
			indent=2,
			sort_keys=True,
		)
		rows.append(
			"<tr class=\"{kind}\" data-kind=\"{kind}\" data-id=\"{rid}\">"
			"<td class=\"kind\">{kind}</td>"
			"<td><code>{category}</code></td>"
			"<td><code class=\"path\">{path}</code></td>"
			"<td>{message}</td>"
			"<td><span class=\"expand-btn\" data-target=\"detail-{rid}\">▸</span></td>"
			"</tr>"
			"<tr id=\"detail-{rid}\" class=\"row-detail hidden\" data-open=\"0\" data-kind=\"{kind}\">"
			"<td colspan=\"5\"><pre>{detail}</pre></td>"
			"</tr>".format(
				kind=c.kind.value,
				rid=row_id,
				category=_html_escape(c.category),
				path=_html_escape(c.path),
				message=_html_escape(c.message),
				detail=_html_escape(detail_payload),
			)
		)

	body_rows = "\n".join(rows) if rows else (
		"<tr><td colspan=\"5\" class=\"empty\">No differences detected.</td></tr>"
	)

	html = (
		"<!doctype html>\n"
		"<html lang=\"en\">\n"
		"<head>\n"
		"<meta charset=\"utf-8\">\n"
		"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
		"<title>flowforge bundle-diff: {old} → {new}</title>\n"
		"<style>{css}</style>\n"
		"</head>\n"
		"<body>\n"
		"<h1>flowforge bundle-diff</h1>\n"
		"<div class=\"meta\"><code>{old}</code> → <code>{new}</code></div>\n"
		"<div class=\"summary\">\n"
		"<span class=\"chip total\">{total} total</span>\n"
		"<span class=\"chip breaking\" data-kind=\"breaking\" data-active=\"true\">{c_breaking} breaking</span>\n"
		"<span class=\"chip requires-coordination\" data-kind=\"requires-coordination\" data-active=\"true\">{c_coord} requires-coordination</span>\n"
		"<span class=\"chip additive\" data-kind=\"additive\" data-active=\"true\">{c_additive} additive</span>\n"
		"</div>\n"
		"<table>\n"
		"<thead><tr><th>Class</th><th>Category</th><th>Path</th><th>Message</th><th></th></tr></thead>\n"
		"<tbody>\n{rows}\n</tbody>\n"
		"</table>\n"
		"<script>{js}</script>\n"
		"</body>\n"
		"</html>\n"
	).format(
		css=_HTML_CSS,
		js=_HTML_JS,
		old=_html_escape(report.old_label),
		new=_html_escape(report.new_label),
		total=len(report.changes),
		c_breaking=counts[ChangeKind.BREAKING.value],
		c_coord=counts[ChangeKind.REQUIRES_COORDINATION.value],
		c_additive=counts[ChangeKind.ADDITIVE.value],
		rows=body_rows,
	)
	return html


# ---------------------------------------------------------------------------
# Text rendering (default)
# ---------------------------------------------------------------------------


def render_text(report: DiffReport) -> str:
	counts = report.counts()
	out: list[str] = []
	out.append(f"bundle-diff: {report.old_label} → {report.new_label}")
	out.append(
		"  totals: "
		f"breaking={counts[ChangeKind.BREAKING.value]}, "
		f"requires-coordination={counts[ChangeKind.REQUIRES_COORDINATION.value]}, "
		f"additive={counts[ChangeKind.ADDITIVE.value]}"
	)
	if not report.changes:
		out.append("  no differences detected.")
		return "\n".join(out) + "\n"
	for c in report.sorted():
		out.append(f"  [{c.kind.value.upper()}] {c.path}: {c.message}")
	return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------


def _load_bundle(path: Path) -> dict[str, Any]:
	"""Load a JSON bundle from *path*. Surfaces friendly errors."""

	try:
		raw = path.read_text(encoding="utf-8")
	except OSError as exc:
		raise typer.BadParameter(f"cannot read {path}: {exc}") from exc
	try:
		obj = json.loads(raw)
	except json.JSONDecodeError as exc:
		raise typer.BadParameter(f"invalid JSON in {path}: {exc}") from exc
	if not isinstance(obj, dict):
		raise typer.BadParameter(f"{path}: top-level must be a JSON object")
	return obj


def bundle_diff_cmd(
	old: Annotated[
		Path,
		typer.Argument(
			exists=True,
			file_okay=True,
			dir_okay=False,
			readable=True,
			help="Path to the OLD JTBD bundle JSON.",
		),
	],
	new: Annotated[
		Path,
		typer.Argument(
			exists=True,
			file_okay=True,
			dir_okay=False,
			readable=True,
			help="Path to the NEW JTBD bundle JSON.",
		),
	],
	html_out: Annotated[
		Path | None,
		typer.Option(
			"--html",
			dir_okay=False,
			help="Write a single-file HTML report to this path.",
		),
	] = None,
	json_out: Annotated[
		Path | None,
		typer.Option(
			"--json",
			dir_okay=False,
			help="Write a deterministic JSON report to this path.",
		),
	] = None,
	exit_zero: Annotated[
		bool,
		typer.Option(
			"--exit-zero",
			help="Always exit 0, even when blocking findings are present.",
		),
	] = False,
) -> None:
	"""Diff two JTBD bundles and categorise each change by deploy-safety class.

	Exit ``0`` if no ``requires-coordination`` or ``breaking`` findings,
	``1`` otherwise (use ``--exit-zero`` to suppress).
	"""

	old_bundle = _load_bundle(old)
	new_bundle = _load_bundle(new)

	report = compute_diff(
		old_bundle,
		new_bundle,
		old_label=str(old),
		new_label=str(new),
	)

	# Always print the text summary so CI logs surface the totals even
	# when --json/--html are used as the consumed artefact.
	typer.echo(render_text(report), nl=False)

	if json_out is not None:
		json_out.write_text(render_json(report), encoding="utf-8")
	if html_out is not None:
		html_out.write_text(render_html(report), encoding="utf-8")

	if report.has_blocking() and not exit_zero:
		raise typer.Exit(1)


def register(app: typer.Typer) -> None:
	"""Mount ``flowforge bundle-diff`` on the root app."""

	app.command(
		"bundle-diff",
		help=(
			"Categorised diff of two JTBD bundles by deploy-safety class "
			"(item 10 of v0.3.0 — improvements.md)."
		),
	)(bundle_diff_cmd)
