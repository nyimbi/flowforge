"""Normalize a parsed JTBD bundle into a generator-friendly view model.

The raw bundle is a faithful 1:1 mirror of the JTBD JSON schema. The
normalized view adds derived fields (state list, transitions, table
name, class name, etc.) so each generator can stay dumb and just
template the precomputed data.

Pure-functional: ``normalize(bundle)`` returns immutable-ish dataclasses
that are safe to render twice and produce identical bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import transforms as T


@dataclass(frozen=True)
class NormalizedField:
	"""Single ``data_capture`` field with derived SA + SQL column shape."""

	id: str
	kind: str
	label: str
	required: bool
	pii: bool
	sa_type: str
	sql_type: str
	ts_component: str
	validation: dict[str, Any]


@dataclass(frozen=True)
class NormalizedDocReq:
	kind: str
	min: int
	max: int | None
	freshness_days: int | None
	av_required: bool


@dataclass(frozen=True)
class NormalizedApproval:
	role: str
	policy: str
	n: int | None
	tier: int | None


@dataclass(frozen=True)
class NormalizedNotification:
	trigger: str
	channel: str
	audience: str


@dataclass(frozen=True)
class NormalizedJTBD:
	"""View-model passed into every generator template."""

	id: str
	title: str
	actor_role: str
	actor_external: bool
	situation: str
	motivation: str
	outcome: str
	success_criteria: tuple[str, ...]
	# Derived identifiers
	class_name: str
	table_name: str
	module_name: str
	url_segment: str
	# Derived workflow shape
	states: tuple[dict[str, Any], ...]
	transitions: tuple[dict[str, Any], ...]
	initial_state: str
	# Per-JTBD aggregates
	fields: tuple[NormalizedField, ...]
	doc_reqs: tuple[NormalizedDocReq, ...]
	approvals: tuple[NormalizedApproval, ...]
	notifications: tuple[NormalizedNotification, ...]
	permissions: tuple[str, ...]
	audit_topics: tuple[str, ...]
	metrics: tuple[str, ...]
	sla_warn_pct: int | None
	sla_breach_seconds: int | None


@dataclass(frozen=True)
class NormalizedProject:
	name: str
	package: str
	domain: str
	tenancy: str
	frontend_framework: str
	languages: tuple[str, ...]
	currencies: tuple[str, ...]
	# v0.3.0 W1 (item 13): chooses Step.tsx emission path. Defaults to
	# "skeleton" so pre-W1 bundles regen byte-identically.
	form_renderer: str = "skeleton"
	# v0.3.0 W2 (item 6): per-bundle idempotency-key TTL in hours. ``None``
	# (default) means use the framework default of 24 hours; the
	# ``idempotency`` generator threads this through to the lookup helper
	# and the router-side replay window. Additive — pre-W2 bundles regen
	# byte-identically.
	idempotency_ttl_hours: int | None = None


@dataclass(frozen=True)
class NormalizedBundle:
	project: NormalizedProject
	shared_roles: tuple[str, ...]
	shared_permissions: tuple[str, ...]
	jtbds: tuple[NormalizedJTBD, ...]
	all_permissions: tuple[str, ...] = field(default_factory=tuple)
	all_audit_topics: tuple[str, ...] = field(default_factory=tuple)
	all_notifications: tuple[NormalizedNotification, ...] = field(default_factory=tuple)


def _norm_field(raw: dict[str, Any]) -> NormalizedField:
	return NormalizedField(
		id=raw["id"],
		kind=raw["kind"],
		label=raw.get("label") or raw["id"].replace("_", " ").title(),
		required=bool(raw.get("required", False)),
		pii=bool(raw.get("pii", False)),
		sa_type=T.SA_COLUMN_TYPE.get(raw["kind"], "String(255)"),
		sql_type=T.SQL_COLUMN_TYPE.get(raw["kind"], "VARCHAR(255)"),
		ts_component=T.TS_FIELD_COMPONENT.get(raw["kind"], "TextField"),
		validation=dict(raw.get("validation") or {}),
	)


def _norm_doc(raw: dict[str, Any]) -> NormalizedDocReq:
	return NormalizedDocReq(
		kind=raw["kind"],
		min=int(raw.get("min", 1)),
		max=raw.get("max"),
		freshness_days=raw.get("freshness_days"),
		av_required=bool(raw.get("av_required", True)),
	)


def _norm_approval(raw: dict[str, Any]) -> NormalizedApproval:
	return NormalizedApproval(
		role=raw["role"],
		policy=raw["policy"],
		n=raw.get("n"),
		tier=raw.get("tier"),
	)


def _norm_notification(raw: dict[str, Any]) -> NormalizedNotification:
	return NormalizedNotification(
		trigger=raw["trigger"],
		channel=raw["channel"],
		audience=raw["audience"],
	)


def _norm_jtbd(raw: dict[str, Any], shared_perms: list[str]) -> NormalizedJTBD:
	jt_id = raw["id"]
	states = T.derive_states(raw)
	transitions = T.derive_transitions(raw, states)
	fields = tuple(_norm_field(f) for f in (raw.get("data_capture") or []))
	docs = tuple(_norm_doc(d) for d in (raw.get("documents_required") or []))
	approvals = tuple(_norm_approval(a) for a in (raw.get("approvals") or []))
	notifications = tuple(_norm_notification(n) for n in (raw.get("notifications") or []))
	perms = tuple(T.derive_permissions(raw, shared_perms))
	audit_topics = tuple(T.derive_audit_topics(raw))

	sla = raw.get("sla") or {}
	return NormalizedJTBD(
		id=jt_id,
		title=raw.get("title") or jt_id.replace("_", " ").title(),
		actor_role=raw["actor"]["role"],
		actor_external=bool(raw["actor"].get("external", False)),
		situation=raw["situation"],
		motivation=raw["motivation"],
		outcome=raw["outcome"],
		success_criteria=tuple(raw.get("success_criteria") or ()),
		class_name=T.pascal_case(jt_id),
		table_name=T.snake_case(jt_id),
		module_name=T.snake_case(jt_id),
		url_segment=T.kebab_case(jt_id),
		states=tuple(states),
		transitions=tuple(transitions),
		initial_state=states[0]["name"],
		fields=fields,
		doc_reqs=docs,
		approvals=approvals,
		notifications=notifications,
		permissions=perms,
		audit_topics=audit_topics,
		metrics=tuple(raw.get("metrics") or ()),
		sla_warn_pct=sla.get("warn_pct"),
		sla_breach_seconds=sla.get("breach_seconds"),
	)


def normalize(bundle: dict[str, Any]) -> NormalizedBundle:
	"""Turn a parsed bundle into the view model used by generators."""

	assert isinstance(bundle, dict), "bundle must be a dict"

	proj = bundle["project"]
	shared = bundle.get("shared") or {}
	shared_perms = list(shared.get("permissions") or [])
	shared_roles = list(shared.get("roles") or [])

	# v0.3.0 W1 (item 13): bundle.project.frontend.form_renderer is the
	# additive knob that picks the Step.tsx emission path. Missing field
	# → "skeleton" so existing bundles regen byte-identically.
	frontend_block = proj.get("frontend") or {}
	form_renderer = str(frontend_block.get("form_renderer", "skeleton"))

	# v0.3.0 W2 (item 6): bundle.project.idempotency.ttl_hours is the
	# additive knob that overrides the framework default replay window.
	# Missing → ``None`` so existing bundles regen byte-identically; the
	# generated helper falls back to the 24h default.
	idempotency_block = proj.get("idempotency") or {}
	raw_ttl = idempotency_block.get("ttl_hours")
	idempotency_ttl_hours = int(raw_ttl) if raw_ttl is not None else None

	project = NormalizedProject(
		name=proj["name"],
		package=proj["package"],
		domain=proj["domain"],
		tenancy=proj.get("tenancy", "single"),
		frontend_framework=proj.get("frontend_framework", "nextjs"),
		languages=tuple(proj.get("languages") or ("en",)),
		currencies=tuple(proj.get("currencies") or ("USD",)),
		form_renderer=form_renderer,
		idempotency_ttl_hours=idempotency_ttl_hours,
	)

	jtbds = tuple(_norm_jtbd(j, shared_perms) for j in bundle["jtbds"])

	# Cross-bundle aggregations: union, sorted, deduplicated.
	all_perms_set: set[str] = set(shared_perms)
	for j in jtbds:
		all_perms_set.update(j.permissions)
	all_perms = tuple(sorted(all_perms_set))

	all_topics_set: set[str] = set()
	for j in jtbds:
		all_topics_set.update(j.audit_topics)
	all_topics = tuple(sorted(all_topics_set))

	# Notifications dedup by (trigger, channel, audience).
	seen: set[tuple[str, str, str]] = set()
	all_notifs: list[NormalizedNotification] = []
	for j in jtbds:
		for n in j.notifications:
			key = (n.trigger, n.channel, n.audience)
			if key in seen:
				continue
			seen.add(key)
			all_notifs.append(n)
	all_notifs.sort(key=lambda n: (n.trigger, n.channel, n.audience))

	return NormalizedBundle(
		project=project,
		shared_roles=tuple(shared_roles),
		shared_permissions=tuple(shared_perms),
		jtbds=jtbds,
		all_permissions=all_perms,
		all_audit_topics=all_topics,
		all_notifications=tuple(all_notifs),
	)
