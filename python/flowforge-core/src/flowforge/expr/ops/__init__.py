"""Built-in operator catalogue.

Each operator is a pure function. Operators run on whatever Python values
the evaluator threads in; the evaluator does no implicit coercion. This
keeps semantics auditable.
"""

from __future__ import annotations

from typing import Any, Callable

OperatorFn = Callable[..., Any]
RegisterFn = Callable[..., None]
"""Callable signature ``(name, fn, *, arity=None) -> None``. The evaluator's
:func:`register_op` matches this; we accept a wider ``Callable[..., None]``
because the registration helper is the only call site."""


def _and(*xs: Any) -> bool:
	return all(bool(x) for x in xs)


def _or(*xs: Any) -> bool:
	return any(bool(x) for x in xs)


def _not(x: Any) -> bool:
	return not bool(x)


def _if(cond: Any, then: Any, else_: Any | None = None) -> Any:
	return then if bool(cond) else else_


def _eq(a: Any, b: Any) -> bool:
	return a == b


def _ne(a: Any, b: Any) -> bool:
	return a != b


def _gt(a: Any, b: Any) -> bool:
	return a > b


def _ge(a: Any, b: Any) -> bool:
	return a >= b


def _lt(a: Any, b: Any) -> bool:
	return a < b


def _le(a: Any, b: Any) -> bool:
	return a <= b


def _add(*xs: Any) -> Any:
	if not xs:
		return 0
	out = xs[0]
	for x in xs[1:]:
		out = out + x
	return out


def _sub(a: Any, b: Any) -> Any:
	return a - b


def _mul(*xs: Any) -> Any:
	out: Any = 1
	for x in xs:
		out = out * x
	return out


def _div(a: Any, b: Any) -> Any:
	return a / b


def _mod(a: Any, b: Any) -> Any:
	return a % b


def _in(needle: Any, haystack: Any) -> bool:
	if haystack is None:
		return False
	return needle in haystack


def _contains(haystack: Any, needle: Any) -> bool:
	return _in(needle, haystack)


def _not_null(x: Any) -> bool:
	return x is not None


def _length(x: Any) -> int:
	if x is None:
		return 0
	return len(x)


def _lower(x: Any) -> str:
	return str(x).lower()


def _upper(x: Any) -> str:
	return str(x).upper()


def _coalesce(*xs: Any) -> Any:
	for x in xs:
		if x is not None:
			return x
	return None


def _is_empty(x: Any) -> bool:
	if x is None:
		return True
	try:
		return len(x) == 0
	except TypeError:
		return False


def _between(x: Any, lo: Any, hi: Any) -> bool:
	return lo <= x <= hi


def _starts_with(s: Any, p: Any) -> bool:
	return str(s).startswith(str(p))


def _ends_with(s: Any, p: Any) -> bool:
	return str(s).endswith(str(p))


def register_builtins(register: RegisterFn) -> None:
	"""Register built-in operators with explicit arity declarations.

	Arity is the ``(min, max)`` count of positional arguments accepted at
	the call site. Variadic operators set ``max=None``. Each declaration
	is enforced both at compile time (``flowforge.compiler.validate``) and
	at runtime (``flowforge.expr.evaluate``) — see audit-2026 E-35 / C-07.
	"""

	register("and", _and, arity=(0, None))
	register("or", _or, arity=(0, None))
	register("not", _not, arity=1)
	register("if", _if, arity=(2, 3))
	register("==", _eq, arity=2)
	register("!=", _ne, arity=2)
	register(">", _gt, arity=2)
	register(">=", _ge, arity=2)
	register("<", _lt, arity=2)
	register("<=", _le, arity=2)
	register("+", _add, arity=(0, None))
	register("-", _sub, arity=2)
	register("*", _mul, arity=(0, None))
	register("/", _div, arity=2)
	register("%", _mod, arity=2)
	register("in", _in, arity=2)
	register("contains", _contains, arity=2)
	register("not_null", _not_null, arity=1)
	register("length", _length, arity=1)
	register("lower", _lower, arity=1)
	register("upper", _upper, arity=1)
	register("coalesce", _coalesce, arity=(0, None))
	register("is_empty", _is_empty, arity=1)
	register("between", _between, arity=3)
	register("starts_with", _starts_with, arity=2)
	register("ends_with", _ends_with, arity=2)
