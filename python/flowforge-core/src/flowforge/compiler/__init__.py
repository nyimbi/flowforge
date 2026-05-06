"""Compiler subpackage: validator + entity-catalog projection + workflow differ."""

from .catalog import EntityRegistry, build_catalog
from .diff import StateChange, TransitionChange, WorkflowDiff, diff_workflow_dicts, diff_workflows
from .validator import ValidationError, ValidationReport, validate

__all__ = [
	"EntityRegistry",
	"StateChange",
	"TransitionChange",
	"ValidationError",
	"ValidationReport",
	"WorkflowDiff",
	"build_catalog",
	"diff_workflow_dicts",
	"diff_workflows",
	"validate",
]
