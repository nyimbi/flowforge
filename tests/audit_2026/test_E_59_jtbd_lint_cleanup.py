"""E-59 — JTBD lint cleanup regression tests (J-10, J-11, J-12).

Audit reference: framework/docs/audit-fix-plan.md §7 E-59.

- **J-10** — ``manifest_from_bundle`` previously caught bare ``Exception``
  when computing ``spec_hash``. Narrowed to ``json.JSONDecodeError`` so
  unrelated errors (encoder bugs, missing imports) are not silently
  swallowed.
- **J-11** — ``DependencyGraph._compute_topological_order`` had a dead
  first attempt computing ``ready`` from forward in-degrees, then
  immediately recomputing from out-degrees. The first attempt is removed.
- **J-12** — ``extract_mentions`` regex was ``@([\\w.-]+)``, which
  matches trailing punctuation and pure-junk identifiers like ``@.``.
  Tightened to require alphanumeric anchors at both ends.
"""

from __future__ import annotations

import inspect

import pytest


# ---------------------------------------------------------------------------
# J-10 — manifest_from_bundle narrows except clause
# ---------------------------------------------------------------------------


def test_J_10_manifest_from_bundle_narrowed_except() -> None:
	"""``manifest_from_bundle`` catches only ``json.JSONDecodeError``."""
	from flowforge_jtbd.registry import manifest as mod

	src = inspect.getsource(mod.manifest_from_bundle)
	# Bare except Exception is forbidden.
	assert "except Exception" not in src, "J-10: bare except Exception still present"
	# Narrowed to JSONDecodeError.
	assert "JSONDecodeError" in src, "J-10: must catch json.JSONDecodeError"


def test_J_10_manifest_from_bundle_invalid_json_returns_none_spec_hash() -> None:
	"""Invalid JSON → spec_hash=None; valid JSON → spec_hash populated."""
	from flowforge_jtbd.registry.manifest import manifest_from_bundle

	# Invalid JSON — JSONDecodeError caught, spec_hash=None.
	bad = manifest_from_bundle("p", "1.0.0", b"not json at all {{")
	assert bad.spec_hash is None
	# Valid JSON — spec_hash is computed.
	good = manifest_from_bundle("p", "1.0.0", b'{"a": 1}')
	assert good.spec_hash is not None
	assert good.spec_hash.startswith("sha256:")


def test_J_10_manifest_from_bundle_unrelated_error_propagates() -> None:
	"""Errors that aren't ``JSONDecodeError`` are re-raised, not swallowed."""
	from flowforge_jtbd.registry import manifest as mod

	# Force canonical_json to raise something unrelated; the bare-except fix
	# must let it through (else we'd still be silently producing spec_hash=None
	# for non-JSON-decode errors, which masks bugs).
	import flowforge_jtbd.dsl.canonical as canonical_mod

	original = canonical_mod.canonical_json

	class _Boom(RuntimeError):
		pass

	def _raises(_data):
		raise _Boom("encoder regression")

	canonical_mod.canonical_json = _raises  # type: ignore[assignment]
	try:
		with pytest.raises(_Boom):
			mod.manifest_from_bundle("p", "1.0.0", b'{"a": 1}')
	finally:
		canonical_mod.canonical_json = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# J-11 — topological order has no dead first attempt
# ---------------------------------------------------------------------------


def test_J_11_topological_order_dead_code_removed() -> None:
	"""``_compute_topological_order`` recomputes ``ready`` exactly once."""
	from flowforge_jtbd.lint import dependencies as deps

	src = inspect.getsource(deps.DependencyGraph._compute_topological_order)
	# Exactly one ``ready = sorted(...)`` assignment, not two.
	assignments = src.count("ready = sorted(")
	assert assignments == 1, (
		f"J-11: expected 1 ``ready = sorted(`` assignment in "
		f"_compute_topological_order, got {assignments}"
	)


def test_J_11_topological_order_still_correct() -> None:
	"""Behaviour preserved: a → b → c yields [c, b, a] (prerequisite-first)."""
	from flowforge_jtbd.lint.dependencies import DependencyGraph

	# Build a tiny graph manually: a requires b, b requires c.
	g = DependencyGraph.__new__(DependencyGraph)
	g.edges = {"a": ["b"], "b": ["c"], "c": []}
	g.cycles = []
	g.issues = []
	g._compute_topological_order()
	assert g.topological_order == ["c", "b", "a"]


# ---------------------------------------------------------------------------
# J-12 — mention regex matches host user-id format
# ---------------------------------------------------------------------------


def test_J_12_mention_regex_accepts_valid_user_ids() -> None:
	from flowforge_jtbd.db.comments import extract_mentions

	cases = {
		"hi @alice": ["alice"],
		"cc @alice.smith @bob_42": ["alice.smith", "bob_42"],
		"hey @user-1!": ["user-1"],
		# UUID7-shaped ids (UMS user_id format)
		"see @018f7c10-5e2a-7000-8000-1234567890ab": ["018f7c10-5e2a-7000-8000-1234567890ab"],
	}
	for body, expected in cases.items():
		assert extract_mentions(body) == expected


def test_J_12_mention_regex_rejects_garbage() -> None:
	"""Trailing punctuation, dot-only, single-char trailing dots are rejected."""
	from flowforge_jtbd.db.comments import extract_mentions

	# trailing punctuation must NOT be captured into the user id
	got = extract_mentions("ping @alice.")  # one trailing dot
	assert got == ["alice"], f"trailing dot leaked into id: {got}"

	# dot-only / dash-only IDs are rejected entirely
	assert extract_mentions("@. is not a mention") == []
	assert extract_mentions("@- is not a mention") == []
	# leading dot is rejected (must start with alnum/_)
	assert extract_mentions("see @.foo") == []

	# Excessive length (>64) is rejected entirely rather than truncated, so we
	# never have to guess which 64 of 100 chars represent the actual user id.
	overlong = "x" * 100
	assert extract_mentions(f"@{overlong}") == []
	# 64 chars exactly: accepted (UUID7 = 36, well below cap).
	exactly_64 = "x" * 64
	assert extract_mentions(f"@{exactly_64} bye") == [exactly_64]
