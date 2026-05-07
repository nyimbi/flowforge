"""JSON-AST expression evaluator.

The expression form is a JSON value:

* Literals: ``null``, ``true``, ``false``, numbers, strings — return themselves.
* ``{"var": "path.to.value"}`` — reads from the supplied context.
* ``{"<op>": [arg1, arg2, ...]}`` — invokes a registered operator with
  evaluated arguments.

Single-argument operators may also pass a single value instead of a list:
``{"not_null": {"var": "x"}}``.

Registry semantics (audit-2026 E-35, findings C-06 / C-07):

* The operator registry is **frozen at module-init**. Post-import calls to
  :func:`register_op` raise :class:`RegistryFrozenError`. This is required
  for replay determinism (architecture invariant 3) — same DSL across two
  evaluator instances must yield byte-identical guard outcomes.
* Every operator declares an arity (min, max) at registration. Calling an
  op with the wrong arity raises :class:`ArityMismatchError`. The
  compile-time validator surfaces these errors before runtime via
  :func:`check_arity`.
"""

from __future__ import annotations

import contextlib
import inspect
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping, NamedTuple

OperatorFn = Callable[..., Any]
Arity = int | tuple[int, int | None]


class EvaluationError(ValueError):
	"""Raised when an expression cannot be evaluated."""


class RegistryFrozenError(RuntimeError):
	"""Raised when ``register_op`` is called after the registry is frozen.

	The expression registry is sealed at module-init time. Post-import
	mutation is rejected because it breaks replay determinism
	(architecture §17 invariant 3): the same DSL applied to the same
	context must produce byte-identical results across instances.
	"""


class ArityMismatchError(ValueError):
	"""Raised when an operator is invoked with the wrong number of arguments.

	Surfaced from the compile-time validator when possible (see
	:func:`check_arity`); raised from the evaluator as a fallback for
	programs that never went through the validator.
	"""


class _OpSpec(NamedTuple):
	"""Internal record bound to each registered operator."""

	name: str
	fn: OperatorFn
	arity_min: int
	arity_max: int | None  # ``None`` denotes unbounded variadic


_OPS_RAW: dict[str, _OpSpec] = {}
_FROZEN: bool = False


def _infer_arity(fn: OperatorFn) -> tuple[int, int | None]:
	"""Infer ``(min, max)`` arity from a callable's signature.

	Handles ``*args`` (max becomes ``None``), positional defaults
	(``max > min``), and plain positional params (``min == max``).
	Keyword-only and ``**kwargs`` are ignored — operators are
	positional-only by convention.
	"""

	sig = inspect.signature(fn)
	min_arity = 0
	max_arity: int | None = 0
	for param in sig.parameters.values():
		if param.kind == inspect.Parameter.VAR_POSITIONAL:
			max_arity = None
			continue
		if param.kind not in (
			inspect.Parameter.POSITIONAL_ONLY,
			inspect.Parameter.POSITIONAL_OR_KEYWORD,
		):
			continue
		if max_arity is not None:
			max_arity += 1
		if param.default is inspect.Parameter.empty:
			min_arity += 1
	return min_arity, max_arity


def _normalize_arity(arity: Arity | None, fn: OperatorFn) -> tuple[int, int | None]:
	if arity is None:
		return _infer_arity(fn)
	if isinstance(arity, int):
		return arity, arity
	lo, hi = arity
	return lo, hi


def register_op(name: str, fn: OperatorFn, *, arity: Arity | None = None) -> None:
	"""Register a pure operator at module-init time.

	``arity`` may be:

	* ``None`` — inferred from ``fn``'s signature (default).
	* an ``int`` — fixed arity (``min == max``).
	* a ``(min, max)`` tuple — ``max=None`` allows variadic.

	After the registry is frozen (post module-init), this raises
	:class:`RegistryFrozenError`.
	"""

	if _FROZEN:
		raise RegistryFrozenError(
			f"cannot register operator {name!r}: expression registry is frozen "
			"(post-startup mutation breaks replay determinism — see audit-2026 E-35)"
		)
	arity_min, arity_max = _normalize_arity(arity, fn)
	if arity_min < 0:
		raise ValueError(f"arity_min must be >= 0, got {arity_min} for {name!r}")
	if arity_max is not None and arity_max < arity_min:
		raise ValueError(
			f"arity_max ({arity_max}) cannot be < arity_min ({arity_min}) for {name!r}"
		)
	_OPS_RAW[name] = _OpSpec(name=name, fn=fn, arity_min=arity_min, arity_max=arity_max)


def _freeze_registry() -> None:
	"""Seal the registry. Called once at module init after builtins register."""

	global _FROZEN
	_FROZEN = True


@contextlib.contextmanager
def _test_only_unfreeze() -> Iterator[None]:
	"""Temporarily unfreeze the registry for a single test scope.

	Snapshot/restore semantics — the registry is restored to its
	pre-context state on exit. This helper exists for unit tests that
	need to register a one-off operator; production code must never
	call it.
	"""

	global _FROZEN
	snapshot = dict(_OPS_RAW)
	was_frozen = _FROZEN
	_FROZEN = False
	try:
		yield
	finally:
		_OPS_RAW.clear()
		_OPS_RAW.update(snapshot)
		_FROZEN = was_frozen


class _OpsProxy(Mapping[str, OperatorFn]):
	"""Read-only ``name -> fn`` mapping over the live registry.

	Backwards-compatible substitute for the old mutable ``_OPS`` dict.
	Mutation attempts (``__setitem__``) are rejected by virtue of
	implementing only the ``Mapping`` protocol.
	"""

	def __getitem__(self, key: str) -> OperatorFn:
		return _OPS_RAW[key].fn

	def __iter__(self) -> Iterator[str]:
		return iter(_OPS_RAW)

	def __len__(self) -> int:
		return len(_OPS_RAW)

	def __contains__(self, key: object) -> bool:
		return key in _OPS_RAW


_OPS: Mapping[str, OperatorFn] = _OpsProxy()


def get_op_spec(name: str) -> _OpSpec | None:
	"""Return the registered :class:`_OpSpec` for *name*, or ``None``."""

	return _OPS_RAW.get(name)


def ops_registry() -> Mapping[str, _OpSpec]:
	"""Public, immutable view of the full registry (for tooling/diagnostics)."""

	return MappingProxyType(_OPS_RAW)


def _is_op_call(node: Any) -> tuple[str, Any] | None:
	if not isinstance(node, dict) or len(node) != 1:
		return None
	((key, val),) = node.items()
	if key in _OPS_RAW or key == "var":
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


def _arity_repr(lo: int, hi: int | None) -> str:
	if hi is None:
		return f">={lo}"
	if lo == hi:
		return f"{lo}"
	return f"{lo}..{hi}"


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

	spec = _OPS_RAW[name]
	if isinstance(raw, list):
		args = [evaluate(a, ctx) for a in raw]
	else:
		args = [evaluate(raw, ctx)]

	n = len(args)
	if n < spec.arity_min or (spec.arity_max is not None and n > spec.arity_max):
		raise ArityMismatchError(
			f"operator {name!r} expects {_arity_repr(spec.arity_min, spec.arity_max)} args, got {n}"
		)
	try:
		return spec.fn(*args)
	except ArityMismatchError:
		raise
	except Exception as exc:  # pragma: no cover — surfaces in validator
		raise EvaluationError(f"operator `{name}` failed: {exc}") from exc


def check_arity(node: Any, *, path: str = "$") -> list[str]:
	"""Walk *node* (JSON expression AST) and report arity violations.

	Returns a list of error messages — empty when the expression is well-formed.
	Unknown op keys are not flagged: they are treated as literal dicts by
	:func:`evaluate`. Cross-runtime unknown-op semantics live in audit-2026
	E-43 (TS↔Python expression conformance).
	"""

	errors: list[str] = []
	_walk_arity(node, path, errors)
	return errors


def _walk_arity(node: Any, path: str, errors: list[str]) -> None:
	if isinstance(node, list):
		for i, child in enumerate(node):
			_walk_arity(child, f"{path}[{i}]", errors)
		return
	if not isinstance(node, dict):
		return
	if len(node) != 1:
		# multi-key dict — never an op call. Recurse into values to catch
		# nested expressions (e.g. inside Effect.values payloads).
		for k, v in node.items():
			_walk_arity(v, f"{path}.{k}", errors)
		return
	((key, val),) = node.items()
	if key == "var":
		return
	spec = _OPS_RAW.get(key)
	if spec is None:
		# unknown op — treated as literal dict by evaluate(); recurse in
		# case sub-expressions live inside.
		_walk_arity(val, f"{path}.{key}", errors)
		return
	if isinstance(val, list):
		n = len(val)
		for i, child in enumerate(val):
			_walk_arity(child, f"{path}.{key}[{i}]", errors)
	else:
		n = 1
		_walk_arity(val, f"{path}.{key}", errors)
	if n < spec.arity_min or (spec.arity_max is not None and n > spec.arity_max):
		errors.append(
			f"operator {key!r} at {path}: expected "
			f"{_arity_repr(spec.arity_min, spec.arity_max)} args, got {n}"
		)


# ---- builtin operator registration ------------------------------------

from . import ops as _ops  # noqa: E402  re-exports do registration

_ops.register_builtins(register_op)
_freeze_registry()
