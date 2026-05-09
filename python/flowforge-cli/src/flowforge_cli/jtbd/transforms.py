"""§5.4 transform table — pure helpers used by the normalizer + generators.

Each function here implements a single deterministic mapping. Kept pure
(no IO, no globals) so the snapshot tests stay byte-stable: same input
in, same output out.
"""

from __future__ import annotations

import re
from typing import Any

# Field kind → SQLAlchemy column type (sqlite-friendly so tests run anywhere).
SA_COLUMN_TYPE: dict[str, str] = {
	"text": "String(512)",
	"textarea": "Text()",
	"email": "String(320)",
	"phone": "String(40)",
	"address": "String(512)",
	"number": "Numeric()",
	"money": "Numeric(18, 2)",
	"date": "Date()",
	"datetime": "DateTime(timezone=True)",
	"enum": "String(64)",
	"boolean": "Boolean()",
	"party_ref": "String(64)",
	"document_ref": "String(64)",
	"signature": "String(128)",
	"file": "String(256)",
}


# Field kind → SQL column type (used by the alembic migration template).
SQL_COLUMN_TYPE: dict[str, str] = {
	"text": "VARCHAR(512)",
	"textarea": "TEXT",
	"email": "VARCHAR(320)",
	"phone": "VARCHAR(40)",
	"address": "VARCHAR(512)",
	"number": "NUMERIC",
	"money": "NUMERIC(18, 2)",
	"date": "DATE",
	"datetime": "TIMESTAMPTZ",
	"enum": "VARCHAR(64)",
	"boolean": "BOOLEAN",
	"party_ref": "VARCHAR(64)",
	"document_ref": "VARCHAR(64)",
	"signature": "VARCHAR(128)",
	"file": "VARCHAR(256)",
}


# Field kind → renderer field component used by ``@flowforge/renderer``.
TS_FIELD_COMPONENT: dict[str, str] = {
	"text": "TextField",
	"textarea": "TextAreaField",
	"email": "TextField",
	"phone": "TextField",
	"address": "TextField",
	"number": "NumberField",
	"money": "MoneyField",
	"date": "DateField",
	"datetime": "DateField",
	"enum": "EnumField",
	"boolean": "BooleanField",
	"party_ref": "LookupField",
	"document_ref": "FileField",
	"signature": "TextField",
	"file": "FileField",
}


# JTBD edge_case.handle → workflow_def state-shape rule.
EDGE_HANDLE_TO_STATE_KIND: dict[str, str] = {
	"branch": "manual_review",
	"reject": "terminal_fail",
	"escalate": "manual_review",
	"compensate": "manual_review",
	"loop": "manual_review",
}


_SAFE_IDENT_RE = re.compile(r"[^a-z0-9_]+")


def snake_case(value: str) -> str:
	"""Lowercase, ``-``/space → ``_``, strip non-alphanumeric.

	Used for python identifiers + table names so we never accidentally
	emit syntax errors when a JTBD id contains punctuation.
	"""

	assert value is not None
	cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
	cleaned = _SAFE_IDENT_RE.sub("_", cleaned)
	cleaned = re.sub(r"_+", "_", cleaned).strip("_")
	return cleaned or "x"


def pascal_case(value: str) -> str:
	"""``claim_intake`` → ``ClaimIntake`` for class names."""

	parts = [p for p in re.split(r"[^A-Za-z0-9]+", value or "") if p]
	if not parts:
		return "X"
	return "".join(p[0].upper() + p[1:] for p in parts)


def kebab_case(value: str) -> str:
	"""``claim_intake`` → ``claim-intake`` for filesystem segments."""

	return snake_case(value).replace("_", "-")


def derive_states(jtbd: dict[str, Any]) -> list[dict[str, Any]]:
	"""§5.4: derive workflow states from a JTBD.

	The base flow is ``intake → review → done`` with two extras:

	* one ``escalated`` manual_review state if any approval policy is
	  ``authority_tier`` (mirrors the claim-large-loss demo)
	* a ``rejected`` terminal_fail state whenever any edge_case.handle
	  is ``reject``
	* one extra branch state per ``edge_case.handle == "branch"``,
	  named after ``edge_case.id`` so transitions can target it
	"""

	states: list[dict[str, Any]] = [
		{"name": "intake", "kind": "manual_review", "swimlane": jtbd["actor"]["role"]},
		{"name": "review", "kind": "manual_review", "swimlane": "reviewer"},
	]

	approvals = jtbd.get("approvals") or []
	if any(a.get("policy") == "authority_tier" for a in approvals):
		states.append({"name": "escalated", "kind": "manual_review", "swimlane": "supervisor"})

	for edge in jtbd.get("edge_cases") or []:
		handle = edge.get("handle")
		if handle == "branch":
			name = snake_case(edge.get("branch_to") or edge.get("id") or "branch")
			if all(s["name"] != name for s in states):
				states.append({"name": name, "kind": "manual_review", "swimlane": "reviewer"})

	if any((e.get("handle") == "reject") for e in jtbd.get("edge_cases") or []):
		states.append({"name": "rejected", "kind": "terminal_fail"})

	# Singleton ``compensated`` terminal_fail — only emitted when at least one
	# edge_case declares ``handle: "compensate"``. The compensation point is
	# the existing ``review`` manual_review state (already in the base flow);
	# the synthesised ``compensate`` transitions fire from there guarded by
	# ``context.<edge_id>`` so reachability validation stays green.
	compensate_edges = [
		e for e in (jtbd.get("edge_cases") or []) if e.get("handle") == "compensate"
	]
	if compensate_edges and all(s["name"] != "compensated" for s in states):
		states.append({"name": "compensated", "kind": "terminal_fail"})

	# Always add the success terminal last.
	states.append({"name": "done", "kind": "terminal_success"})
	return states


def derive_transitions(jtbd: dict[str, Any], states: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Wire transitions: submit, approve, reject (+branches per edge case).

	Adds a permission gate per transition so the lookup-permission
	validator stays happy + the generated app has real-looking RBAC.
	"""

	jt_id = jtbd["id"]
	state_names = {s["name"]: s["kind"] for s in states}
	tr: list[dict[str, Any]] = [
		{
			"id": f"{jt_id}_submit",
			"event": "submit",
			"from_state": "intake",
			"to_state": "review",
			"priority": 0,
			"guards": [],
			"gates": [{"kind": "permission", "permission": f"{jt_id}.submit"}],
			"effects": [
				{"kind": "create_entity", "entity": jt_id},
				{"kind": "audit", "template": f"{jt_id}.submitted"},
			],
		},
		{
			"id": f"{jt_id}_approve",
			"event": "approve",
			"from_state": "review",
			"to_state": "done",
			"priority": 0,
			"guards": [],
			"gates": [{"kind": "permission", "permission": f"{jt_id}.approve"}],
			"effects": [{"kind": "notify", "template": f"{jt_id}.approved"}],
		},
	]

	if "escalated" in state_names:
		tr.append(
			{
				"id": f"{jt_id}_escalate",
				"event": "escalate",
				"from_state": "review",
				"to_state": "escalated",
				"priority": 10,
				"guards": [],
				"gates": [{"kind": "permission", "permission": f"{jt_id}.escalate"}],
				"effects": [{"kind": "audit", "template": f"{jt_id}.escalated"}],
			}
		)
		tr.append(
			{
				"id": f"{jt_id}_escalated_approve",
				"event": "approve",
				"from_state": "escalated",
				"to_state": "done",
				"priority": 0,
				"guards": [],
				"gates": [{"kind": "permission", "permission": f"{jt_id}.approve"}],
				"effects": [{"kind": "notify", "template": f"{jt_id}.approved"}],
			}
		)

	priority = 5
	for edge in jtbd.get("edge_cases") or []:
		handle = edge.get("handle")
		eid = snake_case(edge.get("id") or "edge")
		if handle == "branch":
			target = snake_case(edge.get("branch_to") or eid)
			if target in state_names:
				tr.append(
					{
						"id": f"{jt_id}_{eid}",
						"event": "submit",
						"from_state": "intake",
						"to_state": target,
						"priority": priority,
						"guards": [
							{"kind": "expr", "expr": {"var": f"context.{eid}"}}
						],
						"gates": [{"kind": "permission", "permission": f"{jt_id}.submit"}],
						"effects": [
							{"kind": "audit", "template": f"{jt_id}.{eid}"}
						],
					}
				)
				priority += 1
		elif handle == "reject":
			tr.append(
				{
					"id": f"{jt_id}_{eid}_reject",
					"event": "reject",
					"from_state": "review",
					"to_state": "rejected",
					"priority": priority,
					"guards": [],
					"gates": [{"kind": "permission", "permission": f"{jt_id}.reject"}],
					"effects": [{"kind": "audit", "template": f"{jt_id}.{eid}_rejected"}],
				}
			)
			priority += 1
		elif handle == "loop":
			tr.append(
				{
					"id": f"{jt_id}_{eid}_loop",
					"event": "request_more_info",
					"from_state": "review",
					"to_state": "intake",
					"priority": priority,
					"guards": [],
					"gates": [{"kind": "permission", "permission": f"{jt_id}.review"}],
					"effects": [{"kind": "audit", "template": f"{jt_id}.{eid}_returned"}],
				}
			)
			priority += 1

	# ----------------------------------------------------------------------
	# Compensation synthesis (item 2 / W0).
	#
	# For every edge_case declaring ``handle: "compensate"``, emit a paired
	# compensation transition that reverses the forward saga in LIFO order.
	# The pairing rules are deterministic functions of the *already-synthesised*
	# transitions above, so two regens against the same bundle produce
	# byte-identical output regardless of dict iteration timing.
	# ----------------------------------------------------------------------
	compensate_edges = [
		e for e in (jtbd.get("edge_cases") or []) if e.get("handle") == "compensate"
	]
	if compensate_edges:
		# Walk the forward transitions in synthesis order, collect the
		# compensable effects in encounter order, then reverse for LIFO.
		# create_entity → compensate_delete (same entity field).
		# notify       → notify_cancellation (template "<jtbd>.<event>.cancelled").
		# Each compensable forward effect becomes a ``kind=compensate`` effect
		# with ``compensation_kind`` naming the saga-step kind the host
		# registers a handler for (matches the engine's fire.py wire-up of
		# instance.saga.append({"kind": compensation_kind, ...})).
		paired: list[dict[str, Any]] = []
		for fwd in tr:
			fwd_event = fwd.get("event") or ""
			for eff in fwd.get("effects") or ():
				kind = eff.get("kind")
				if kind == "create_entity":
					paired.append(
						{
							"kind": "compensate",
							"compensation_kind": "compensate_delete",
							"values": {"entity": eff.get("entity") or jt_id},
						}
					)
				elif kind == "notify":
					paired.append(
						{
							"kind": "compensate",
							"compensation_kind": "notify_cancellation",
							"values": {"template": f"{jt_id}.{fwd_event}.cancelled"},
						}
					)
		paired_lifo = list(reversed(paired))

		for edge in compensate_edges:
			eid = snake_case(edge.get("id") or "edge")
			# Compensate transitions all fire from ``review`` (the compensation
			# point) on event ``compensate``, distinguished by guard
			# ``context.<eid>`` — same expr shape ``branch`` already uses, so
			# no new operator is introduced into ``flowforge.expr`` (cross-
			# runtime parity fixture stays untouched).
			tr.append(
				{
					"id": f"{jt_id}_{eid}_compensate",
					"event": "compensate",
					"from_state": "review",
					"to_state": "compensated",
					"priority": priority,
					"guards": [
						{"kind": "expr", "expr": {"var": f"context.{eid}"}}
					],
					"gates": [{"kind": "permission", "permission": f"{jt_id}.review"}],
					"effects": list(paired_lifo),
				}
			)
			priority += 1
	return tr


def field_to_sa_column(field: dict[str, Any]) -> tuple[str, str, bool]:
	"""Return ``(name, sa_column_expr, nullable)``.

	The column expression is what gets dropped into a ``Mapped[...]`` line
	in the SQLAlchemy model template.
	"""

	col_type = SA_COLUMN_TYPE.get(field["kind"], "String(255)")
	nullable = not field.get("required", False)
	return field["id"], col_type, nullable


def field_to_sql_column(field: dict[str, Any]) -> tuple[str, str, bool]:
	"""Return ``(name, sql_type, nullable)`` for the alembic migration."""

	col_type = SQL_COLUMN_TYPE.get(field["kind"], "VARCHAR(255)")
	nullable = not field.get("required", False)
	return field["id"], col_type, nullable


def field_to_form_field(field: dict[str, Any]) -> dict[str, Any]:
	"""Map a JTBD ``data_capture`` field to a form_spec field."""

	out: dict[str, Any] = {
		"id": field["id"],
		"kind": field["kind"],
		"label": field.get("label") or field["id"].replace("_", " ").title(),
		"required": bool(field.get("required", False)),
		"pii": bool(field.get("pii", False)),
	}
	if field.get("validation"):
		out["validation"] = field["validation"]
	return out


def derive_permissions(jtbd: dict[str, Any], shared_perms: list[str]) -> list[str]:
	"""Per-JTBD permission set: read/submit/approve/reject/review/escalate.

	Any permission already declared in ``shared.permissions`` is filtered
	out — the cross-bundle aggregator de-duplicates the union later.
	"""

	jt_id = jtbd["id"]
	base = [
		f"{jt_id}.read",
		f"{jt_id}.submit",
		f"{jt_id}.review",
		f"{jt_id}.approve",
	]
	if any(e.get("handle") == "reject" for e in jtbd.get("edge_cases") or []):
		base.append(f"{jt_id}.reject")
	if any(a.get("policy") == "authority_tier" for a in jtbd.get("approvals") or []):
		base.append(f"{jt_id}.escalate")
	return [p for p in base if p not in set(shared_perms or [])]


def derive_audit_topics(jtbd: dict[str, Any]) -> list[str]:
	"""Audit-event topic strings emitted by this JTBD's transitions."""

	jt_id = jtbd["id"]
	topics = [f"{jt_id}.submitted", f"{jt_id}.approved"]
	for edge in jtbd.get("edge_cases") or []:
		eid = snake_case(edge.get("id") or "edge")
		handle = edge.get("handle")
		if handle == "branch":
			topics.append(f"{jt_id}.{eid}")
		elif handle == "reject":
			topics.append(f"{jt_id}.{eid}_rejected")
		elif handle == "loop":
			topics.append(f"{jt_id}.{eid}_returned")
	if any(a.get("policy") == "authority_tier" for a in jtbd.get("approvals") or []):
		topics.append(f"{jt_id}.escalated")
	return sorted(set(topics))
