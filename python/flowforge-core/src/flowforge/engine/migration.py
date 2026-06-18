"""Instance state migration between workflow definition versions.

When a workflow definition evolves (states renamed, removed, or added),
running instances may have a ``state`` that no longer exists in the new
definition.  :func:`migrate_instance` applies a host-supplied mapping to
advance the instance to a valid state in the new definition.

Usage::

    from flowforge.engine.migration import migrate_instance, StateMigrationError

    mapping = {"old_state": "new_state", "deprecated_state": "terminal_fail"}
    migrate_instance(old_wd, new_wd, instance, state_mapping=mapping)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..dsl.workflow_def import WorkflowDef
from ..engine.fire import Instance

_log = logging.getLogger(__name__)


class StateMigrationError(ValueError):
	"""Raised when an instance cannot be migrated to the new definition."""


@dataclass
class MigrationReport:
	"""Result of a migration attempt."""

	instance_id: str
	from_version: str
	to_version: str
	from_state: str
	to_state: str
	context_changes: dict[str, Any]
	warnings: list[str]


def validate_migration_mapping(
	old_wd: WorkflowDef,
	new_wd: WorkflowDef,
	state_mapping: dict[str, str],
) -> list[str]:
	"""Return a list of validation errors in *state_mapping*.

	An empty list means the mapping is valid.
	"""
	errors: list[str] = []
	old_state_names = {s.name for s in old_wd.states}
	new_state_names = {s.name for s in new_wd.states}

	for old_name, new_name in state_mapping.items():
		if old_name not in old_state_names:
			errors.append(f"source state {old_name!r} not in old definition {old_wd.version!r}")
		if new_name not in new_state_names:
			errors.append(f"target state {new_name!r} not in new definition {new_wd.version!r}")

	# Check for unmapped states that exist in old but not new
	removed = old_state_names - new_state_names - set(state_mapping)
	if removed:
		errors.append(
			f"states removed in {new_wd.version!r} but not mapped: {sorted(removed)}"
		)

	return errors


def migrate_instance(
	old_wd: WorkflowDef,
	new_wd: WorkflowDef,
	instance: Instance,
	*,
	state_mapping: dict[str, str] | None = None,
	context_defaults: dict[str, Any] | None = None,
	allow_same_version: bool = False,
) -> MigrationReport:
	"""Migrate *instance* from *old_wd* to *new_wd* in place.

	Args:
		old_wd: The definition the instance was created under.
		new_wd: The definition to migrate to (must have same ``key``).
		instance: Instance to migrate. Mutated in place.
		state_mapping: Maps old state names → new state names for states
		               that were renamed. States that exist unchanged in
		               both definitions need no mapping entry.
		context_defaults: Default values for new context fields added in
		                  *new_wd*. Missing keys stay as ``None``.
		allow_same_version: If ``False`` (default), migrating a definition
		                    to itself raises :class:`StateMigrationError`.

	Raises:
		StateMigrationError: If the instance state cannot be migrated.
	"""
	if old_wd.key != new_wd.key:
		raise StateMigrationError(
			f"definition key mismatch: {old_wd.key!r} vs {new_wd.key!r}"
		)
	if not allow_same_version and old_wd.version == new_wd.version:
		raise StateMigrationError(
			f"old and new definition are the same version {old_wd.version!r}; "
			"pass allow_same_version=True to force"
		)

	state_mapping = state_mapping or {}
	context_defaults = context_defaults or {}

	new_state_names = {s.name for s in new_wd.states}

	# Resolve the new state for the instance
	current_state = instance.state
	if current_state in new_state_names:
		# State still valid in new definition — no mapping needed
		new_state = current_state
	elif current_state in state_mapping:
		new_state = state_mapping[current_state]
		if new_state not in new_state_names:
			raise StateMigrationError(
				f"mapped target state {new_state!r} does not exist in {new_wd.version!r}"
			)
	else:
		raise StateMigrationError(
			f"instance {instance.id!r} is in state {current_state!r} which does not "
			f"exist in {new_wd.version!r} and has no entry in state_mapping"
		)

	# Apply context defaults for any new keys
	context_changes: dict[str, Any] = {}
	for key, default in context_defaults.items():
		if key not in instance.context:
			instance.context[key] = default
			context_changes[key] = default

	warnings: list[str] = []

	# Mutate instance state
	from_state = instance.state
	instance.state = new_state
	instance.history.append(
		f"migrated:{old_wd.version}→{new_wd.version}:{from_state}→{new_state}"
	)

	if from_state != new_state:
		_log.info(
			"instance %r migrated: state %r → %r (def %r → %r)",
			instance.id, from_state, new_state, old_wd.version, new_wd.version,
		)

	return MigrationReport(
		instance_id=instance.id,
		from_version=old_wd.version,
		to_version=new_wd.version,
		from_state=from_state,
		to_state=new_state,
		context_changes=context_changes,
		warnings=warnings,
	)
