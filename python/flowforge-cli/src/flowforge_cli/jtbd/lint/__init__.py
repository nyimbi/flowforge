"""JTBD linter — composition-time semantic checks.

E-5 (this module) ships the conflict solver: cross-JTBD reasoning over
the ``(timing, data, consistency)`` tuple that each JTBD declares about
the entities it touches. Sister linters (lifecycle, dependency,
actor — see E-4) live in adjacent modules.
"""

from __future__ import annotations

from flowforge_cli.jtbd.lint.conflicts import (
	ConflictIssue,
	ConflictSolver,
	JtbdSemantics,
	PairsConflictSolver,
	Z3ConflictSolver,
	default_solver,
	detect_conflicts,
	extract_semantics,
)

__all__ = [
	"ConflictIssue",
	"ConflictSolver",
	"JtbdSemantics",
	"PairsConflictSolver",
	"Z3ConflictSolver",
	"default_solver",
	"detect_conflicts",
	"extract_semantics",
]
