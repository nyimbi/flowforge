"""Whitelisted expression evaluator.

Expressions are JSON-serializable. The runtime never executes arbitrary
Python; every operator is a pure function in :mod:`flowforge.expr.ops`.
"""

from .evaluator import EvaluationError, evaluate, register_op

__all__ = ["EvaluationError", "evaluate", "register_op"]
