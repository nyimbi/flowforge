"""Tests for receive_signal, sla_scheduler, and migrate_instance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from flowforge import config
from flowforge.dsl import WorkflowDef
from flowforge.engine import (
	MigrationReport,
	SlaBreachResult,
	SlaCandidate,
	StateMigrationError,
	check_sla_breaches,
	fire,
	is_sla_breached,
	migrate_instance,
	new_instance,
	receive_signal,
	validate_migration_mapping,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approval_def(version: str = "1.0.0") -> WorkflowDef:
	return WorkflowDef.model_validate({
		"key": "approval",
		"version": version,
		"subject_kind": "request",
		"initial_state": "pending",
		"states": [
			{"name": "pending", "kind": "signal_wait"},
			{"name": "approved", "kind": "terminal_success"},
			{"name": "rejected", "kind": "terminal_fail"},
		],
		"transitions": [
			{
				"id": "approve",
				"event": "approve",
				"from_state": "pending",
				"to_state": "approved",
				"priority": 0,
			},
			{
				"id": "reject",
				"event": "reject",
				"from_state": "pending",
				"to_state": "rejected",
				"priority": 0,
			},
		],
	})


def _sla_def() -> WorkflowDef:
	return WorkflowDef.model_validate({
		"key": "sla_flow",
		"version": "1.0.0",
		"subject_kind": "ticket",
		"initial_state": "open",
		"states": [
			{
				"name": "open",
				"kind": "manual_review",
				"sla": {"breach_seconds": 3600},
			},
			{"name": "closed", "kind": "terminal_success"},
			{"name": "escalated", "kind": "manual_review"},
		],
		"transitions": [
			{
				"id": "close",
				"event": "close",
				"from_state": "open",
				"to_state": "closed",
				"priority": 0,
			},
			{
				"id": "breach",
				"event": "sla_breach",
				"from_state": "open",
				"to_state": "escalated",
				"priority": 0,
			},
			{
				"id": "close_escalated",
				"event": "close",
				"from_state": "escalated",
				"to_state": "closed",
				"priority": 0,
			},
		],
	})


def _renamed_def() -> WorkflowDef:
	"""v2: 'pending' renamed to 'waiting', 'approved' kept."""
	return WorkflowDef.model_validate({
		"key": "approval",
		"version": "2.0.0",
		"subject_kind": "request",
		"initial_state": "waiting",
		"states": [
			{"name": "waiting", "kind": "signal_wait"},
			{"name": "approved", "kind": "terminal_success"},
			{"name": "rejected", "kind": "terminal_fail"},
		],
		"transitions": [
			{
				"id": "approve",
				"event": "approve",
				"from_state": "waiting",
				"to_state": "approved",
				"priority": 0,
			},
			{
				"id": "reject",
				"event": "reject",
				"from_state": "waiting",
				"to_state": "rejected",
				"priority": 0,
			},
		],
	})


# ---------------------------------------------------------------------------
# receive_signal
# ---------------------------------------------------------------------------

async def test_receive_signal_advances_signal_wait_instance():
	config.reset_to_fakes()
	wd = _approval_def()
	instance = new_instance(wd)
	assert instance.state == "pending"

	result = await receive_signal(
		wd, instance, "approve", payload={}, dispatch_ports=False
	)
	assert result.new_state == "approved"


async def test_receive_signal_reject_path():
	config.reset_to_fakes()
	wd = _approval_def()
	instance = new_instance(wd)

	result = await receive_signal(
		wd, instance, "reject", payload={}, dispatch_ports=False
	)
	assert result.new_state == "rejected"


async def test_receive_signal_raises_if_not_signal_wait():
	config.reset_to_fakes()
	wd = _approval_def()
	instance = new_instance(wd)
	# advance to terminal
	await fire(wd, instance, "approve", dispatch_ports=False)

	with pytest.raises(ValueError, match="signal_wait"):
		await receive_signal(wd, instance, "approve", dispatch_ports=False)


async def test_receive_signal_raises_if_state_not_in_def():
	config.reset_to_fakes()
	wd = _approval_def()
	instance = new_instance(wd)
	instance.state = "nonexistent_state"

	with pytest.raises(ValueError, match="signal_wait"):
		await receive_signal(wd, instance, "approve", dispatch_ports=False)


# ---------------------------------------------------------------------------
# is_sla_breached
# ---------------------------------------------------------------------------

def test_is_sla_breached_false_when_within_threshold():
	wd = _sla_def()
	instance = new_instance(wd)
	now = datetime.now(timezone.utc)
	candidate = SlaCandidate(
		instance=instance,
		wd=wd,
		state_entered_at=now - timedelta(seconds=1800),
	)
	breached, elapsed = is_sla_breached(candidate, now=now)
	assert not breached
	assert elapsed == 1800


def test_is_sla_breached_true_when_over_threshold():
	wd = _sla_def()
	instance = new_instance(wd)
	now = datetime.now(timezone.utc)
	candidate = SlaCandidate(
		instance=instance,
		wd=wd,
		state_entered_at=now - timedelta(seconds=4000),
	)
	breached, elapsed = is_sla_breached(candidate, now=now)
	assert breached
	assert elapsed >= 3600


def test_is_sla_breached_false_for_state_with_no_sla():
	wd = _approval_def()
	instance = new_instance(wd)
	now = datetime.now(timezone.utc)
	candidate = SlaCandidate(
		instance=instance,
		wd=wd,
		state_entered_at=now - timedelta(seconds=99999),
	)
	breached, elapsed = is_sla_breached(candidate, now=now)
	assert not breached
	assert elapsed == 0


# ---------------------------------------------------------------------------
# check_sla_breaches
# ---------------------------------------------------------------------------

async def test_check_sla_breaches_fires_on_overdue_instance():
	config.reset_to_fakes()
	wd = _sla_def()
	instance = new_instance(wd)
	now = datetime.now(timezone.utc)

	candidates = [
		SlaCandidate(
			instance=instance,
			wd=wd,
			state_entered_at=now - timedelta(seconds=5000),
		)
	]
	results = await check_sla_breaches(candidates, now=now, dispatch_ports=False)
	assert len(results) == 1
	assert results[0].fired is True
	assert results[0].instance_id == instance.id
	assert results[0].elapsed >= 3600


async def test_check_sla_breaches_skips_non_breached():
	config.reset_to_fakes()
	wd = _sla_def()
	instance = new_instance(wd)
	now = datetime.now(timezone.utc)

	candidates = [
		SlaCandidate(
			instance=instance,
			wd=wd,
			state_entered_at=now - timedelta(seconds=100),
		)
	]
	results = await check_sla_breaches(candidates, now=now, dispatch_ports=False)
	assert results == []


async def test_check_sla_breaches_records_error_on_fire_failure():
	config.reset_to_fakes()
	wd = _sla_def()
	instance = new_instance(wd)
	# Move to terminal state — sla_breach event has no transition there
	await fire(wd, instance, "close", dispatch_ports=False)
	assert instance.state == "closed"

	now = datetime.now(timezone.utc)
	candidates = [
		SlaCandidate(
			instance=instance,
			wd=wd,
			state_entered_at=now - timedelta(seconds=5000),
		)
	]
	# closed state has no SLA → skipped, not an error
	results = await check_sla_breaches(candidates, now=now, dispatch_ports=False)
	assert results == []


# ---------------------------------------------------------------------------
# validate_migration_mapping
# ---------------------------------------------------------------------------

def test_validate_migration_mapping_valid():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	errors = validate_migration_mapping(old_wd, new_wd, {"pending": "waiting"})
	assert errors == []


def test_validate_migration_mapping_bad_source():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	errors = validate_migration_mapping(old_wd, new_wd, {"ghost_state": "waiting"})
	assert any("ghost_state" in e for e in errors)


def test_validate_migration_mapping_bad_target():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	errors = validate_migration_mapping(old_wd, new_wd, {"pending": "nonexistent"})
	assert any("nonexistent" in e for e in errors)


def test_validate_migration_mapping_unmapped_removed_state():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	# pass empty mapping — 'pending' was removed, not mapped
	errors = validate_migration_mapping(old_wd, new_wd, {})
	assert any("pending" in e for e in errors)


# ---------------------------------------------------------------------------
# migrate_instance
# ---------------------------------------------------------------------------

def test_migrate_instance_renames_state():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	instance = new_instance(old_wd)
	assert instance.state == "pending"

	report = migrate_instance(
		old_wd, new_wd, instance, state_mapping={"pending": "waiting"}
	)
	assert instance.state == "waiting"
	assert report.from_state == "pending"
	assert report.to_state == "waiting"
	assert report.from_version == "1.0.0"
	assert report.to_version == "2.0.0"


def test_migrate_instance_identity_if_state_exists_in_new():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	instance = new_instance(old_wd)
	# manually put instance in 'approved' — which still exists in v2
	instance.state = "approved"

	report = migrate_instance(old_wd, new_wd, instance, state_mapping={"pending": "waiting"})
	assert instance.state == "approved"
	assert report.from_state == "approved"
	assert report.to_state == "approved"


def test_migrate_instance_raises_for_unmapped_state():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	instance = new_instance(old_wd)
	# no mapping provided for 'pending'
	with pytest.raises(StateMigrationError, match="pending"):
		migrate_instance(old_wd, new_wd, instance, state_mapping={})


def test_migrate_instance_raises_for_same_version():
	wd = _approval_def("1.0.0")
	instance = new_instance(wd)
	with pytest.raises(StateMigrationError, match="same version"):
		migrate_instance(wd, wd, instance)


def test_migrate_instance_allow_same_version_flag():
	wd = _approval_def("1.0.0")
	instance = new_instance(wd)
	report = migrate_instance(wd, wd, instance, allow_same_version=True)
	assert report.to_version == "1.0.0"


def test_migrate_instance_applies_context_defaults():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	instance = new_instance(old_wd)
	instance.state = "approved"

	report = migrate_instance(
		old_wd, new_wd, instance,
		state_mapping={"pending": "waiting"},
		context_defaults={"new_field": "default_val"},
	)
	assert instance.context["new_field"] == "default_val"
	assert report.context_changes == {"new_field": "default_val"}


def test_migrate_instance_does_not_overwrite_existing_context():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	instance = new_instance(old_wd, initial_context={"existing": "kept"})
	instance.state = "approved"

	migrate_instance(
		old_wd, new_wd, instance,
		state_mapping={"pending": "waiting"},
		context_defaults={"existing": "should_not_overwrite"},
	)
	assert instance.context["existing"] == "kept"


def test_migrate_instance_appends_history():
	old_wd = _approval_def("1.0.0")
	new_wd = _renamed_def()
	instance = new_instance(old_wd)
	migrate_instance(old_wd, new_wd, instance, state_mapping={"pending": "waiting"})
	assert any("migrated:" in h for h in instance.history)


def test_migrate_instance_raises_key_mismatch():
	old_wd = _approval_def("1.0.0")
	other_wd = WorkflowDef.model_validate({
		"key": "other_flow",
		"version": "2.0.0",
		"subject_kind": "request",
		"initial_state": "start",
		"states": [{"name": "start", "kind": "automatic"}, {"name": "done", "kind": "terminal_success"}],
		"transitions": [{"id": "go", "event": "go", "from_state": "start", "to_state": "done", "priority": 0}],
	})
	instance = new_instance(old_wd)
	with pytest.raises(StateMigrationError, match="key mismatch"):
		migrate_instance(old_wd, other_wd, instance)
