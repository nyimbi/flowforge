"""Whitelisted expression evaluator.

Expressions are JSON-serializable. The runtime never executes arbitrary
Python; every operator is a pure function in :mod:`flowforge.expr.ops`.

The registry is sealed at module-init for replay determinism (audit-2026
E-35 / architecture invariant 3); see :mod:`flowforge.expr.evaluator`
for the semantics of :class:`RegistryFrozenError` and
:class:`ArityMismatchError`.
"""

from .evaluator import (
	ArityMismatchError,
	EvaluationError,
	RegistryFrozenError,
	check_arity,
	evaluate,
	ops_registry,
	register_op,
)

__all__ = [
	"ArityMismatchError",
	"EvaluationError",
	"RegistryFrozenError",
	"check_arity",
	"evaluate",
	"ops_registry",
	"register_op",
]
