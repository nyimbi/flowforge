"""Tests for flowforge_jtbd.audit — E-20 JTBD-edit audit trail."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from flowforge_jtbd.audit import (
	JtbdAuditLogger,
	JtbdEditAction,
	build_audit_event,
	diff_spec_keys,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(jtbd_id: str = "claim_intake", **overrides: Any) -> dict[str, Any]:
	s: dict[str, Any] = {
		"id": jtbd_id,
		"situation": "policyholder files an FNOL",
		"motivation": "recover losses",
		"outcome": "claim accepted",
	}
	s.update(overrides)
	return s


def _run(coro: Any) -> Any:
	return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# diff_spec_keys
# ---------------------------------------------------------------------------


def test_diff_keys_no_changes() -> None:
	s = _spec()
	assert diff_spec_keys(s, s) == []


def test_diff_keys_added_key() -> None:
	old = _spec()
	new = {**_spec(), "sla": {"breach_seconds": 3600}}
	assert "sla" in diff_spec_keys(old, new)


def test_diff_keys_removed_key() -> None:
	old = {**_spec(), "title": "File a claim"}
	new = _spec()
	assert "title" in diff_spec_keys(old, new)


def test_diff_keys_changed_value() -> None:
	old = _spec(outcome="claim accepted")
	new = _spec(outcome="claim queued for triage")
	assert "outcome" in diff_spec_keys(old, new)


def test_diff_keys_both_none_returns_empty() -> None:
	assert diff_spec_keys(None, None) == []


def test_diff_keys_old_none_all_new_keys() -> None:
	new = _spec()
	keys = diff_spec_keys(None, new)
	assert set(keys) == set(new.keys())


def test_diff_keys_sorted() -> None:
	old = _spec()
	new = {**_spec(), "zzz": 1, "aaa": 2}
	keys = diff_spec_keys(old, new)
	assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# build_audit_event
# ---------------------------------------------------------------------------


def test_build_event_created() -> None:
	evt = build_audit_event(
		JtbdEditAction.created,
		jtbd_id="claim_intake",
		version="1.0.0",
		actor_id="user-1",
		tenant_id="tenant-A",
		new_spec=_spec(),
	)
	assert evt.kind == "jtbd.spec_version.created"
	assert evt.subject_kind == "jtbd_spec_version"
	assert evt.subject_id == "claim_intake@1.0.0"
	assert evt.payload["jtbd_id"] == "claim_intake"
	assert evt.payload["version"] == "1.0.0"
	assert evt.payload["actor_id"] == "user-1"
	assert evt.payload["old_hash"] is None
	assert evt.payload["new_hash"] is not None
	assert evt.payload["new_hash"].startswith("sha256:")


def test_build_event_edited_has_both_hashes() -> None:
	old = _spec(outcome="old outcome")
	new = _spec(outcome="new outcome")
	evt = build_audit_event(
		JtbdEditAction.edited,
		jtbd_id="claim_intake",
		version="1.1.0",
		actor_id="user-2",
		tenant_id="tenant-A",
		old_spec=old,
		new_spec=new,
	)
	assert evt.payload["old_hash"] != evt.payload["new_hash"]
	assert "outcome" in evt.payload["diff_keys"]


def test_build_event_deprecated_no_spec() -> None:
	evt = build_audit_event(
		JtbdEditAction.deprecated,
		jtbd_id="old_intake",
		version="1.0.0",
		actor_id="curator-1",
		tenant_id="tenant-A",
	)
	assert evt.kind == "jtbd.spec_version.deprecated"
	assert evt.payload["old_hash"] is None
	assert evt.payload["new_hash"] is None
	assert evt.payload["diff_keys"] == []


def test_build_event_extra_fields_merged() -> None:
	evt = build_audit_event(
		JtbdEditAction.replaced_by_set,
		jtbd_id="old_intake",
		version="1.0.0",
		actor_id="user-1",
		tenant_id="tenant-A",
		extra={"replaced_by": "new_intake"},
	)
	assert evt.payload["replaced_by"] == "new_intake"


def test_build_event_ai_drafted() -> None:
	evt = build_audit_event(
		JtbdEditAction.ai_drafted,
		jtbd_id="ai_claim",
		version="0.1.0",
		actor_id="system",
		tenant_id="tenant-B",
		new_spec=_spec("ai_claim"),
	)
	assert evt.kind == "jtbd.spec_version.ai_drafted"


# ---------------------------------------------------------------------------
# JtbdEditAction enum
# ---------------------------------------------------------------------------


def test_all_nine_actions_defined() -> None:
	actions = list(JtbdEditAction)
	assert len(actions) == 9
	names = {a.value for a in actions}
	expected = {
		"created", "edited", "submitted", "approved", "rejected",
		"deprecated", "archived", "replaced_by_set", "ai_drafted",
	}
	assert names == expected


# ---------------------------------------------------------------------------
# JtbdAuditLogger — buffered (no config.audit wired)
# ---------------------------------------------------------------------------


def test_logger_buffers_when_no_sink() -> None:
	logger = JtbdAuditLogger(tenant_id="tenant-1")
	event_id = _run(logger.record(
		JtbdEditAction.created,
		jtbd_id="claim_intake",
		version="1.0.0",
		actor_id="user-1",
		new_spec=_spec(),
	))
	assert event_id == "buffered"
	assert len(logger.buffered) == 1
	assert logger.buffered[0].kind == "jtbd.spec_version.created"


def test_logger_record_created_helper() -> None:
	logger = JtbdAuditLogger(tenant_id="tenant-1")
	_run(logger.record_created("claim_intake", "1.0.0", "user-1", spec=_spec()))
	assert len(logger.buffered) == 1
	assert logger.buffered[0].payload["new_hash"] is not None


def test_logger_record_edited_computes_diff() -> None:
	logger = JtbdAuditLogger(tenant_id="tenant-1")
	old = _spec(outcome="old")
	new = _spec(outcome="new")
	_run(logger.record_edited("claim_intake", "1.1.0", "user-2", old_spec=old, new_spec=new))
	evt = logger.buffered[0]
	assert "outcome" in evt.payload["diff_keys"]


def test_logger_record_deprecated_includes_replaced_by() -> None:
	logger = JtbdAuditLogger(tenant_id="tenant-1")
	_run(logger.record_deprecated(
		"old_intake", "1.0.0", "curator-1", replaced_by="new_intake"
	))
	evt = logger.buffered[0]
	assert evt.payload.get("replaced_by") == "new_intake"
	assert evt.kind == "jtbd.spec_version.deprecated"


def test_logger_tenant_id_in_every_event() -> None:
	logger = JtbdAuditLogger(tenant_id="my-tenant")
	_run(logger.record(JtbdEditAction.submitted, "x", "1.0.0", "user-1"))
	assert logger.buffered[0].tenant_id == "my-tenant"


# ---------------------------------------------------------------------------
# Hash stability
# ---------------------------------------------------------------------------


def test_identical_specs_produce_same_hash() -> None:
	s = _spec()
	evt1 = build_audit_event(
		JtbdEditAction.created, jtbd_id="x", version="1", actor_id="u", tenant_id="t",
		new_spec=s,
	)
	evt2 = build_audit_event(
		JtbdEditAction.edited, jtbd_id="x", version="1", actor_id="u", tenant_id="t",
		old_spec=s, new_spec=s,
	)
	assert evt1.payload["new_hash"] == evt2.payload["old_hash"] == evt2.payload["new_hash"]
	assert evt2.payload["diff_keys"] == []
