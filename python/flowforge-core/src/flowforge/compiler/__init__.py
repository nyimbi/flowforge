"""Compiler subpackage: validator, entity-catalog projection, workflow
differ, and the incremental rebuild compiler."""

from .build_lockfile import (
	BuildLockEntry,
	BuildLockfile,
	LOCKFILE_SCHEMA_VERSION,
	hash_bytes,
	hash_inputs,
)
from .catalog import EntityRegistry, build_catalog
from .diff import StateChange, TransitionChange, WorkflowDiff, diff_workflow_dicts, diff_workflows
from .incremental import (
	ApplyResult,
	BuildPlan,
	FileStore,
	FileTarget,
	IncrementalCompiler,
	InMemoryFileStore,
	LocalFileStore,
	PlanEntry,
	PlanEntryStatus,
)
from .validator import ValidationError, ValidationReport, validate

__all__ = [
	"ApplyResult",
	"BuildLockEntry",
	"BuildLockfile",
	"BuildPlan",
	"EntityRegistry",
	"FileStore",
	"FileTarget",
	"IncrementalCompiler",
	"InMemoryFileStore",
	"LOCKFILE_SCHEMA_VERSION",
	"LocalFileStore",
	"PlanEntry",
	"PlanEntryStatus",
	"StateChange",
	"TransitionChange",
	"ValidationError",
	"ValidationReport",
	"WorkflowDiff",
	"build_catalog",
	"diff_workflow_dicts",
	"diff_workflows",
	"hash_bytes",
	"hash_inputs",
	"validate",
]
