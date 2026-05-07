"""Tests for ``flowforge_jtbd.lint.conflicts`` (E-5).

Covers both backends: the always-available pairs solver and the Z3
solver when ``python-z3-solver`` is installed (skipped otherwise).
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from flowforge_jtbd.lint import (
	JtbdSemantics,
	PairsConflictSolver,
	Z3ConflictSolver,
	default_solver,
	detect_conflicts,
	extract_semantics,
)
from flowforge_jtbd.lint.results import Issue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _account_open() -> JtbdSemantics:
	return JtbdSemantics(
		jtbd_id="account_open",
		timing="realtime",
		data="write",
		consistency="strong",
		entities=("account",),
	)


def _nightly_recompute(consistency: str = "eventual") -> JtbdSemantics:
	return JtbdSemantics(
		jtbd_id="nightly_balance_recompute",
		timing="batch",
		data="write",
		consistency=consistency,  # type: ignore[arg-type]
		entities=("account",),
	)


def _read_balance() -> JtbdSemantics:
	return JtbdSemantics(
		jtbd_id="read_balance",
		timing="realtime",
		data="read",
		consistency="strong",
		entities=("account",),
	)


# ---------------------------------------------------------------------------
# Pair rule: warning + error cases
# ---------------------------------------------------------------------------


def test_pairs_combined_consistency_unclear_warns() -> None:
	# realtime+write+strong vs batch+write+eventual on same entity → warn.
	issues = PairsConflictSolver().detect([_account_open(), _nightly_recompute()])
	assert len(issues) == 1
	issue = issues[0]
	assert isinstance(issue, Issue)
	assert issue.severity == "warning"
	assert issue.rule == "combined_consistency_unclear"
	assert issue.related_jtbds == ["account_open", "nightly_balance_recompute"]
	assert issue.extra["entity"] == "account"
	assert issue.fixhint is not None


def test_pairs_strong_in_batch_path_errors() -> None:
	issues = PairsConflictSolver().detect(
		[_account_open(), _nightly_recompute(consistency="strong")]
	)
	assert len(issues) == 1
	assert issues[0].severity == "error"
	assert issues[0].rule == "strong_consistency_in_batch_path"
	assert issues[0].extra["entity"] == "account"


# ---------------------------------------------------------------------------
# Negative cases
# ---------------------------------------------------------------------------


def test_pairs_no_conflict_on_disjoint_entities() -> None:
	a = _account_open()
	b = JtbdSemantics(
		jtbd_id="ledger_post",
		timing="batch",
		data="write",
		consistency="strong",
		entities=("ledger",),  # disjoint
	)
	assert PairsConflictSolver().detect([a, b]) == []


def test_pairs_readers_not_flagged() -> None:
	r1 = _read_balance()
	r2 = JtbdSemantics(
		jtbd_id="report_balance_nightly",
		timing="batch",
		data="read",
		consistency="eventual",
		entities=("account",),
	)
	assert PairsConflictSolver().detect([r1, r2]) == []


def test_pairs_one_reader_one_writer_skipped() -> None:
	assert PairsConflictSolver().detect([_account_open(), _read_balance()]) == []


def test_pairs_same_tuple_no_conflict() -> None:
	a = _account_open()
	b = JtbdSemantics(
		jtbd_id="account_freeze",
		timing="realtime",
		data="write",
		consistency="strong",
		entities=("account",),
	)
	assert PairsConflictSolver().detect([a, b]) == []


# ---------------------------------------------------------------------------
# Multi-entity / dedupe
# ---------------------------------------------------------------------------


def test_pairs_dedupes_across_shared_entities() -> None:
	a = JtbdSemantics(
		jtbd_id="a",
		timing="realtime",
		data="write",
		consistency="strong",
		entities=("e1", "e2"),
	)
	b = JtbdSemantics(
		jtbd_id="b",
		timing="batch",
		data="write",
		consistency="eventual",
		entities=("e1", "e2"),
	)
	issues = PairsConflictSolver().detect([a, b])
	assert len(issues) == 1
	assert issues[0].rule == "combined_consistency_unclear"
	# Entity is the alphabetically first shared one.
	assert issues[0].extra["entity"] == "e1"


def test_pairs_orders_errors_before_warnings() -> None:
	# Three JTBDs on `account`:
	#   a: realtime+write+strong
	#   b: batch+write+strong  → error vs a
	#   c: batch+write+eventual → warning vs a (b vs c is not a rule pair)
	a = _account_open()
	b = _nightly_recompute(consistency="strong")
	c = JtbdSemantics(
		jtbd_id="z_late",
		timing="batch",
		data="write",
		consistency="eventual",
		entities=("account",),
	)
	issues = PairsConflictSolver().detect([a, b, c])
	assert [i.severity for i in issues] == ["error", "warning"]
	assert issues[0].rule == "strong_consistency_in_batch_path"
	assert issues[1].rule == "combined_consistency_unclear"


# ---------------------------------------------------------------------------
# Z3 backend — gated per-test so the non-Z3 suite still runs without it
# ---------------------------------------------------------------------------


def _has_z3() -> bool:
	try:
		import z3  # noqa: F401
	except ImportError:
		return False
	return True


_REQUIRES_Z3 = pytest.mark.skipif(
	not _has_z3(), reason="python-z3-solver not installed"
)


@_REQUIRES_Z3
def test_z3_matches_pairs_on_warning_case() -> None:
	pair_issues = PairsConflictSolver().detect([_account_open(), _nightly_recompute()])
	z3_issues = Z3ConflictSolver().detect([_account_open(), _nightly_recompute()])
	assert pair_issues == z3_issues


@_REQUIRES_Z3
def test_z3_matches_pairs_on_error_case() -> None:
	args = [_account_open(), _nightly_recompute(consistency="strong")]
	assert PairsConflictSolver().detect(args) == Z3ConflictSolver().detect(args)


@_REQUIRES_Z3
def test_z3_matches_pairs_on_clean_case() -> None:
	assert PairsConflictSolver().detect(
		[_account_open(), _read_balance()]
	) == Z3ConflictSolver().detect([_account_open(), _read_balance()])


# ---------------------------------------------------------------------------
# default_solver / detect_conflicts top-level
# ---------------------------------------------------------------------------


@_REQUIRES_Z3
def test_default_solver_picks_z3_when_available() -> None:
	chosen = default_solver()
	assert chosen.backend == "z3"


def test_default_solver_falls_back_when_z3_missing(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Force the default-picker to think z3 is missing.
	import importlib

	from flowforge_jtbd.lint import conflicts as mod

	real_import = importlib.__import__

	def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
		if name == "z3":
			raise ImportError("blocked for test")
		return real_import(name, *args, **kwargs)

	monkeypatch.delitem(sys.modules, "z3", raising=False)
	monkeypatch.setattr("builtins.__import__", fake_import)
	chosen = mod.default_solver()
	assert chosen.backend == "pairs"


def test_detect_conflicts_routes_through_default() -> None:
	issues = detect_conflicts([_account_open(), _nightly_recompute()])
	assert len(issues) == 1
	assert issues[0].rule == "combined_consistency_unclear"


def test_detect_conflicts_partition_falls_back_to_pairs() -> None:
	# Synthesize a single-entity component above the §23.10 threshold.
	semantics = [
		JtbdSemantics(
			jtbd_id=f"j{i}",
			timing="realtime",
			data="write",
			consistency="strong",
			entities=("hot_entity",),
		)
		for i in range(60)  # > _PAIRS_FALLBACK_THRESHOLD (50)
	]
	issues = detect_conflicts(semantics)
	assert issues == []  # no rule violations across the cohort


def test_detect_conflicts_explicit_pairs_solver() -> None:
	issues = detect_conflicts(
		[_account_open(), _nightly_recompute()],
		solver=PairsConflictSolver(),
	)
	assert len(issues) == 1


# ---------------------------------------------------------------------------
# extract_semantics — composition input
# ---------------------------------------------------------------------------


def test_extract_semantics_basic() -> None:
	composition = {
		"jtbds": [
			{
				"id": "account_open",
				"semantics": {
					"timing": "realtime",
					"data": "write",
					"consistency": "strong",
					"entities": ["account"],
				},
			},
			# Skipped: no semantics block.
			{"id": "audit_export"},
		]
	}
	out = extract_semantics(composition)
	assert len(out) == 1
	assert out[0].jtbd_id == "account_open"
	assert out[0].entities == ("account",)


def test_extract_semantics_empty() -> None:
	assert extract_semantics({}) == []
	assert extract_semantics({"jtbds": []}) == []


def test_extract_semantics_rejects_bad_timing() -> None:
	composition = {
		"jtbds": [
			{
				"id": "x",
				"semantics": {
					"timing": "instant",  # not in TIMINGS
					"data": "write",
					"consistency": "strong",
					"entities": ["e"],
				},
			}
		]
	}
	with pytest.raises(ValueError, match="bad timing"):
		extract_semantics(composition)


def test_extract_semantics_rejects_missing_id() -> None:
	composition = {
		"jtbds": [
			{
				"semantics": {
					"timing": "realtime",
					"data": "write",
					"consistency": "strong",
				}
			}
		]
	}
	with pytest.raises(ValueError, match="missing 'id'"):
		extract_semantics(composition)


def test_extract_semantics_rejects_missing_key() -> None:
	composition = {
		"jtbds": [
			{
				"id": "x",
				"semantics": {
					"timing": "realtime",
					"data": "write",
					# consistency missing
					"entities": ["e"],
				},
			}
		]
	}
	with pytest.raises(ValueError, match="missing key 'consistency'"):
		extract_semantics(composition)


# ---------------------------------------------------------------------------
# JtbdSemantics validation
# ---------------------------------------------------------------------------


def test_jtbd_semantics_rejects_bad_values() -> None:
	with pytest.raises(AssertionError):
		JtbdSemantics(
			jtbd_id="x",
			timing="instant",  # type: ignore[arg-type]
			data="write",
			consistency="strong",
			entities=("e",),
		)
	with pytest.raises(AssertionError):
		JtbdSemantics(
			jtbd_id="",
			timing="realtime",
			data="write",
			consistency="strong",
			entities=("e",),
		)
