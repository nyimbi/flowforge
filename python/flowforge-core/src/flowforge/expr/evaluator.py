"""JSON-AST expression evaluator.

The expression form is a JSON value:

* Literals: ``null``, ``true``, ``false``, numbers, strings — return themselves.
* ``{"var": "path.to.value"}`` — reads from the supplied context.
* ``{"<op>": [arg1, arg2, ...]}`` — invokes a registered operator with
  evaluated arguments.

Single-argument operators may also pass a single value instead of a list:
``{"not_null": {"var": "x"}}``.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

OperatorFn = Callable[..., Any]


class EvaluationError(ValueError):
	"""Raised when an expression cannot be evaluated."""


_OPS: dict[str, OperatorFn] = {}


def register_op(name: str, fn: OperatorFn) -> None:
	"""Register a pure operator. Replaces any prior op of the same name."""
	_OPS[name] = fn


def _is_op_call(node: Any) -> tuple[str, Any] | None:
	if not isinstance(node, dict) or len(node) != 1:
		return None
	((key, val),) = node.items()
	if key in _OPS or key == "var":
		return key, val
	return None


def _resolve_var(path: str, ctx: dict[str, Any]) -> Any:
	cur: Any = ctx
	for part in path.split("."):
		if isinstance(cur, dict) and part in cur:
			cur = cur[part]
		elif isinstance(cur, list):
			try:
				cur = cur[int(part)]
			except (ValueError, IndexError):
				return None
		else:
			return None
	return cur


def evaluate(node: Any, ctx: dict[str, Any]) -> Any:
	"""Evaluate *node* in the given *ctx* dictionary."""

	op = _is_op_call(node)
	if op is None:
		# literal
		return node

	name, raw = op
	if name == "var":
		if not isinstance(raw, str):
			raise EvaluationError(f"`var` requires string path, got {type(raw).__name__}")
		return _resolve_var(raw, ctx)

	fn = _OPS[name]
	if isinstance(raw, list):
		args = [evaluate(a, ctx) for a in raw]
	else:
		args = [evaluate(raw, ctx)]
	try:
		return fn(*args)
	except Exception as exc:  # pragma: no cover — surfaces in validator
		raise EvaluationError(f"operator `{name}` failed: {exc}") from exc


# ---- builtin operator registration ------------------------------------

from . import ops as _ops  # noqa: E402  re-exports do registration

_ops.register_builtins(register_op)
