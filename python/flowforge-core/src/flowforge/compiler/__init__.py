"""Compiler subpackage: validator + entity-catalog projection."""

from .validator import ValidationError, ValidationReport, validate
from .catalog import EntityRegistry, build_catalog

__all__ = [
	"EntityRegistry",
	"ValidationError",
	"ValidationReport",
	"build_catalog",
	"validate",
]
