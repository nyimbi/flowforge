"""JTBD-edit audit trail — first-class audited objects (E-20).

Wires JTBD spec-version edits into the existing ``flowforge.config.audit``
sink so that every JTBD edit is part of the hash-chain audit log alongside
workflow events.

Every JTBD action produces an :class:`~flowforge.ports.types.AuditEvent`
with::

    subject_kind = "jtbd_spec_version"
    kind         = f"jtbd.spec_version.{action}"
    payload      = {
        "jtbd_id":   <str>,
        "version":   <str>,
        "old_hash":  <str | None>,   # sha256:… of old canonical JSON
        "new_hash":  <str | None>,   # sha256:… of new canonical JSON
        "diff_keys": [<str>],        # top-level dict keys that changed
        "actor_id":  <str>,
        ...extra                     # caller-supplied metadata
    }

The hash chain is maintained by the ``AuditSink`` implementation
(``flowforge-audit-pg`` by default).  Chains are verifiable via::

    flowforge audit verify --subject-kind jtbd_spec_version

Canonical action list (per evolution.md §25.3):

    created | edited | submitted | approved | rejected |
    deprecated | archived | replaced_by_set | ai_drafted
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from flowforge.ports.types import AuditEvent


# ---------------------------------------------------------------------------
# Action enum
# ---------------------------------------------------------------------------


class JtbdEditAction(str, Enum):
	"""Audit actions for a ``jtbd_spec_version`` subject."""

	created = "created"
	edited = "edited"
	submitted = "submitted"
	approved = "approved"
	rejected = "rejected"
	deprecated = "deprecated"
	archived = "archived"
	replaced_by_set = "replaced_by_set"
	ai_drafted = "ai_drafted"


# ---------------------------------------------------------------------------
# Diff helper
# ---------------------------------------------------------------------------


def diff_spec_keys(
	old: dict[str, Any] | None,
	new: dict[str, Any] | None,
) -> list[str]:
	"""Return sorted list of top-level keys that changed between *old* and *new*.

	A key is "changed" if it is present in one dict but not the other, or if
	its value differs.  ``None`` on either side means "spec did not exist"
	(e.g., on ``created`` or ``archived``).
	"""
	if old is None and new is None:
		return []
	old = old or {}
	new = new or {}
	all_keys = set(old) | set(new)
	return sorted(k for k in all_keys if old.get(k) != new.get(k))


# ---------------------------------------------------------------------------
# Event factory
# ---------------------------------------------------------------------------


def build_audit_event(
	action: JtbdEditAction,
	jtbd_id: str,
	version: str,
	actor_id: str,
	tenant_id: str,
	*,
	old_spec: dict[str, Any] | None = None,
	new_spec: dict[str, Any] | None = None,
	extra: dict[str, Any] | None = None,
) -> AuditEvent:
	"""Build an :class:`AuditEvent` for a JTBD spec-version action.

	:param action: The audit action (e.g. ``JtbdEditAction.edited``).
	:param jtbd_id: Stable JTBD identifier (snake_case, per spec schema).
	:param version: Semver of the JTBD spec being acted on.
	:param actor_id: User id of the actor performing the action.
	:param tenant_id: Owning tenant.
	:param old_spec: Previous spec dict (``None`` on ``created``).
	:param new_spec: Updated spec dict (``None`` on ``archived``).
	:param extra: Additional metadata merged into the payload.
	"""
	assert jtbd_id, "jtbd_id must be non-empty"
	assert version, "version must be non-empty"
	assert actor_id, "actor_id must be non-empty"
	assert tenant_id, "tenant_id must be non-empty"

	old_hash: str | None = None
	new_hash: str | None = None

	if old_spec is not None:
		from .dsl.canonical import spec_hash as _hash
		old_hash = _hash(old_spec)

	if new_spec is not None:
		from .dsl.canonical import spec_hash as _hash
		new_hash = _hash(new_spec)

	payload: dict[str, Any] = {
		"jtbd_id": jtbd_id,
		"version": version,
		"old_hash": old_hash,
		"new_hash": new_hash,
		"diff_keys": diff_spec_keys(old_spec, new_spec),
		"actor_id": actor_id,
	}
	if extra:
		payload.update(extra)

	return AuditEvent(
		kind=f"jtbd.spec_version.{action.value}",
		subject_kind="jtbd_spec_version",
		subject_id=f"{jtbd_id}@{version}",
		tenant_id=tenant_id,
		actor_user_id=actor_id,
		payload=payload,
	)


# ---------------------------------------------------------------------------
# JtbdAuditLogger
# ---------------------------------------------------------------------------


class JtbdAuditLogger:
	"""Thin wrapper that records JTBD audit events through ``flowforge.config.audit``.

	Hosts call this from their JTBD service layer; the logger delegates to
	the configured audit sink so the hash chain is maintained automatically.

	If ``flowforge.config.audit`` is ``None`` (dev / test), events are
	collected in :attr:`buffered` for inspection without raising.

	Usage::

	    from flowforge_jtbd.audit import JtbdAuditLogger, JtbdEditAction

	    logger = JtbdAuditLogger(tenant_id="tenant-1")

	    await logger.record(
	        JtbdEditAction.edited,
	        jtbd_id="claim_intake",
	        version="1.1.0",
	        actor_id="user-42",
	        old_spec=old_dict,
	        new_spec=new_dict,
	    )
	"""

	def __init__(self, tenant_id: str) -> None:
		assert tenant_id, "tenant_id must be non-empty"
		self.tenant_id = tenant_id
		self.buffered: list[AuditEvent] = []

	async def record(
		self,
		action: JtbdEditAction,
		jtbd_id: str,
		version: str,
		actor_id: str,
		*,
		old_spec: dict[str, Any] | None = None,
		new_spec: dict[str, Any] | None = None,
		extra: dict[str, Any] | None = None,
	) -> str:
		"""Build and dispatch a JTBD audit event.

		Returns the event id assigned by the audit sink, or ``"buffered"``
		when no sink is configured.
		"""
		evt = build_audit_event(
			action,
			jtbd_id=jtbd_id,
			version=version,
			actor_id=actor_id,
			tenant_id=self.tenant_id,
			old_spec=old_spec,
			new_spec=new_spec,
			extra=extra,
		)

		import flowforge.config as _cfg
		if _cfg.audit is not None:
			return await _cfg.audit.record(evt)

		# Fallback: buffer for testing / dev.
		self.buffered.append(evt)
		return "buffered"

	async def record_created(
		self,
		jtbd_id: str,
		version: str,
		actor_id: str,
		*,
		spec: dict[str, Any],
		extra: dict[str, Any] | None = None,
	) -> str:
		return await self.record(
			JtbdEditAction.created,
			jtbd_id=jtbd_id,
			version=version,
			actor_id=actor_id,
			new_spec=spec,
			extra=extra,
		)

	async def record_edited(
		self,
		jtbd_id: str,
		version: str,
		actor_id: str,
		*,
		old_spec: dict[str, Any],
		new_spec: dict[str, Any],
		extra: dict[str, Any] | None = None,
	) -> str:
		return await self.record(
			JtbdEditAction.edited,
			jtbd_id=jtbd_id,
			version=version,
			actor_id=actor_id,
			old_spec=old_spec,
			new_spec=new_spec,
			extra=extra,
		)

	async def record_deprecated(
		self,
		jtbd_id: str,
		version: str,
		actor_id: str,
		*,
		replaced_by: str | None = None,
		extra: dict[str, Any] | None = None,
	) -> str:
		merged_extra: dict[str, Any] = {"replaced_by": replaced_by} if replaced_by else {}
		if extra:
			merged_extra.update(extra)
		return await self.record(
			JtbdEditAction.deprecated,
			jtbd_id=jtbd_id,
			version=version,
			actor_id=actor_id,
			extra=merged_extra or None,
		)


__all__ = [
	"JtbdAuditLogger",
	"JtbdEditAction",
	"build_audit_event",
	"diff_spec_keys",
]
