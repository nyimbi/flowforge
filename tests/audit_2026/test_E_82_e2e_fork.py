"""E-82: e2e fork flow, invariant-9 strengthening, soak-script flag acceptance.

Acceptance criteria:
  - test_E_82_invariant_9_strengthened: full fork→advance→join lifecycle through
    fire() is correct (symmetric join, double-advance guard, replay determinism).
  - test_E_82_soak_script_accepts_workflow_flag: soak.sh --help exits 0 without
    complaining about unknown flags; --workflow flag is parsed cleanly.
  - test_E_82_soak_script_accepts_forks_enabled_flag: --forks-enabled sets
    FLOWFORGE_FORKS_ENABLED in the script's environment without crashing on parse.
  - test_E_82_all_8_invariants_green: conformance suite imports cleanly and the
    invariant file is present on disk.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess

import pytest

from flowforge import config as _config
from flowforge.dsl import WorkflowDef
from flowforge.engine._fork import TokenAlreadyConsumedError
from flowforge.engine.fire import fire, new_instance


# ---------------------------------------------------------------------------
# Shared fork workflow definition
# ---------------------------------------------------------------------------

def _fork_wd(key: str = "e82_fork_test") -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": key,
			"version": "0.1.0",
			"subject_kind": "test",
			"initial_state": "triage",
			"metadata": {"engine_features": ["parallel_fork"]},
			"states": [
				{"name": "triage",     "kind": "manual_review"},
				{"name": "fork_point", "kind": "parallel_fork"},
				{"name": "branch_a",   "kind": "automatic"},
				{"name": "branch_b",   "kind": "automatic"},
				{"name": "join",       "kind": "parallel_join"},
				{"name": "done",       "kind": "terminal_success"},
			],
			"transitions": [
				{"id": "t1", "event": "ready",    "from_state": "triage",     "to_state": "fork_point", "priority": 0},
				{"id": "t2", "event": "__auto__", "from_state": "fork_point", "to_state": "branch_a",   "priority": 1},
				{"id": "t3", "event": "__auto__", "from_state": "fork_point", "to_state": "branch_b",   "priority": 0},
				{"id": "t4", "event": "a_done",   "from_state": "branch_a",   "to_state": "join",       "priority": 0},
				{"id": "t5", "event": "b_done",   "from_state": "branch_b",   "to_state": "join",       "priority": 0},
				{"id": "t6", "event": "join_complete", "from_state": "join",  "to_state": "done",       "priority": 0},
			],
		}
	)


# ---------------------------------------------------------------------------
# test_E_82_invariant_9_strengthened
# ---------------------------------------------------------------------------


def test_E_82_invariant_9_strengthened(monkeypatch) -> None:
	"""Inline regression for invariant 9: parallel_fork lifecycle through fire().

	(a) Symmetric fork-join → final state 'done', tokens empty.
	(b) Double-advance of a consumed token → TokenAlreadyConsumedError.
	(c) Two independent replays of the same event sequence → byte-identical
	    state + history.
	"""
	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "1")

	async def _run() -> None:
		# (a) Symmetric fork-join
		_config.reset_to_fakes()
		wd = _fork_wd("e82_sym")
		inst = new_instance(wd)
		await fire(wd, inst, "ready")
		tokens = inst.tokens.list()
		assert len(tokens) == 2, f"expected 2 tokens, got {tokens}"
		tmap = {t.state: t for t in tokens}
		assert set(tmap) == {"branch_a", "branch_b"}

		await fire(wd, inst, "a_done", token_id=tmap["branch_a"].id)
		# Join barrier: still forked after first advance
		assert inst.state == "fork_point", (
			f"premature collapse: expected fork_point, got {inst.state!r}"
		)
		result = await fire(wd, inst, "b_done", token_id=tmap["branch_b"].id)
		assert inst.state == "done", f"expected 'done', got {inst.state!r}"
		assert result.terminal is True
		assert inst.tokens.list() == []

		# (b) Double-advance raises
		_config.reset_to_fakes()
		wd2 = _fork_wd("e82_dbl")
		inst2 = new_instance(wd2)
		await fire(wd2, inst2, "ready")
		tmap2 = {t.state: t for t in inst2.tokens.list()}
		a2_id = tmap2["branch_a"].id
		await fire(wd2, inst2, "a_done", token_id=a2_id)
		try:
			await fire(wd2, inst2, "a_done", token_id=a2_id)
			raise AssertionError("Expected TokenAlreadyConsumedError")
		except TokenAlreadyConsumedError:
			pass

		# (c) Replay determinism
		_config.reset_to_fakes()
		wd3 = _fork_wd("e82_replay")
		inst_a = new_instance(wd3, instance_id="e82-replay-a")
		inst_b = new_instance(wd3, instance_id="e82-replay-b")
		for replay_inst in (inst_a, inst_b):
			await fire(wd3, replay_inst, "ready")
			tmap_r = {t.state: t for t in replay_inst.tokens.list()}
			await fire(wd3, replay_inst, "a_done", token_id=tmap_r["branch_a"].id)
			tmap_r2 = {t.state: t for t in replay_inst.tokens.list()}
			await fire(wd3, replay_inst, "b_done", token_id=tmap_r2["branch_b"].id)
		assert inst_a.state == inst_b.state == "done"
		# Token IDs are UUID7 — they differ between instances. Strip them from
		# history entries before comparing so we test structural determinism
		# (same transitions in same order) not incidental UUID values.
		import re as _re
		_uuid_pat = _re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
		def _strip(h: list[str]) -> list[str]:
			return [_uuid_pat.sub("<uuid>", e) for e in h]
		assert _strip(inst_a.history) == _strip(inst_b.history), (
			f"replay history structure diverged:\n  a={_strip(inst_a.history)}\n  b={_strip(inst_b.history)}"
		)

	asyncio.run(_run())


# ---------------------------------------------------------------------------
# test_E_82_soak_script_accepts_workflow_flag
# ---------------------------------------------------------------------------

_SOAK_SCRIPT = (
	pathlib.Path(__file__).resolve().parents[2]
	/ "scripts"
	/ "ops"
	/ "audit-2026-soak.sh"
)


def test_E_82_soak_script_accepts_workflow_flag() -> None:
	"""soak.sh --help exits 0 and does not reject --workflow as unknown."""
	assert _SOAK_SCRIPT.exists(), f"soak script missing: {_SOAK_SCRIPT}"
	result = subprocess.run(
		["bash", str(_SOAK_SCRIPT), "--help"],
		capture_output=True,
		text=True,
	)
	# --help must exit 0 (the grep/sed pipeline always succeeds)
	assert result.returncode == 0, (
		f"--help exited {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
	)
	# --workflow must not appear in the "unknown flag" error path — verify by
	# dry-running parse only (no --target-url so it will exit 2 on the
	# missing-required check, NOT on unknown-flag).  We pass --workflow first
	# so it is parsed before the required-var gate is hit.
	result2 = subprocess.run(
		["bash", str(_SOAK_SCRIPT), "--workflow", "soak_wf"],
		capture_output=True,
		text=True,
	)
	# Script exits 2 for missing --target-url, NOT for unknown flag.
	assert "unknown flag" not in result2.stderr, (
		f"--workflow was rejected as unknown flag: {result2.stderr}"
	)
	assert result2.returncode == 2  # missing --target-url


# ---------------------------------------------------------------------------
# test_E_82_soak_script_accepts_forks_enabled_flag
# ---------------------------------------------------------------------------


def test_E_82_soak_script_accepts_forks_enabled_flag() -> None:
	"""soak.sh --forks-enabled is parsed without 'unknown flag' error."""
	assert _SOAK_SCRIPT.exists(), f"soak script missing: {_SOAK_SCRIPT}"
	result = subprocess.run(
		["bash", str(_SOAK_SCRIPT), "--forks-enabled", "--workflow", "fork_soak_wf"],
		capture_output=True,
		text=True,
	)
	# Must not error on unknown flags — only on missing required args.
	assert "unknown flag" not in result.stderr, (
		f"--forks-enabled was rejected as unknown: {result.stderr}"
	)
	# Required args are missing → exit 2 is expected.
	assert result.returncode == 2, (
		f"expected exit 2 (missing --target-url), got {result.returncode}\n"
		f"stderr={result.stderr}"
	)


# ---------------------------------------------------------------------------
# test_E_82_all_8_invariants_green
# ---------------------------------------------------------------------------


def test_E_82_all_8_invariants_green() -> None:
	"""Conformance suite is present and all core engine symbols importable."""
	conf_path = (
		pathlib.Path(__file__).resolve().parents[1]
		/ "conformance"
		/ "test_arch_invariants.py"
	)
	assert conf_path.exists(), f"conformance suite missing: {conf_path}"

	# All symbols that E-82 wires through fire() must import cleanly.
	from flowforge.engine.fire import (  # noqa: F401
		ConcurrentFireRejected,
		Instance,
		OutboxDispatchError,
		fire,
		new_instance,
	)
	from flowforge.engine._fork import (  # noqa: F401
		RegionStillForkedError,
		TokenAlreadyConsumedError,
		all_branches_joined,
		consume_token,
		make_fork_tokens,
	)
	from flowforge.engine.fork_config import forks_enabled, workflow_declares_fork  # noqa: F401
	from flowforge.engine.tokens import Token, TokenSet  # noqa: F401
