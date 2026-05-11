"""CI gate — v0.3.0 W4b / item 22 / ADR-002.

ADR-002 (``docs/v0.3.0-engineering/adr/ADR-002-copy-override-sidecar.md``)
states:

> The file is **a committed artifact**. CI fails if
> ``flowforge polish-copy`` is invoked and the resulting file is
> uncommitted (``git status --porcelain`` check).

This test asserts that invariant against every example bundle:

1. Capture ``git status --porcelain`` baseline (the test must not be
   sensitive to unrelated dirty state; it filters its assertion to the
   ``examples/`` tree only).
2. Run ``flowforge polish-copy --commit`` against each example bundle.
   In CI no ``ANTHROPIC_API_KEY``/``CLAUDE_API_KEY`` is set, so the
   command degrades to a no-op echo and does not write a sidecar.
3. Re-capture ``git status --porcelain`` and assert that the
   ``examples/`` portion is unchanged — no new ``*.overrides.json``
   files appear, no existing sidecar is mutated.

The test also acts as a smoke test: each example bundle is exercised
by the command, validating that the CLI's resolve-precedence and
no-op-echo paths work end-to-end against the real example bundles
in the repo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES_DIR = _REPO_ROOT / "examples"
_EXAMPLES = (
	"building-permit",
	"hiring-pipeline",
	"insurance_claim",
)


def _examples_status(cwd: Path) -> str:
	"""Return ``git status --porcelain examples/`` for *cwd*.

	Filters to the examples tree so unrelated dirty state in the repo
	(open work, untracked notepads, etc.) doesn't poison the assertion.
	"""

	res = subprocess.run(
		["git", "status", "--porcelain", "--", "examples/"],
		cwd=cwd,
		capture_output=True,
		text=True,
		check=True,
	)
	return res.stdout


def _run_polish_copy(bundle: Path, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
	"""Invoke ``flowforge polish-copy --commit`` against *bundle* with a
	scrubbed env (no API key) so the command runs the no-op echo path."""

	# Use the workspace-installed CLI; this mirrors what
	# ``scripts/check_all.sh`` step 8 calls. ``uv run flowforge ...``
	# is the canonical entry point in the repo.
	return subprocess.run(
		[
			"uv",
			"run",
			"flowforge",
			"polish-copy",
			"--bundle",
			str(bundle),
			"--tone",
			"formal-professional",
			"--commit",
		],
		cwd=_REPO_ROOT,
		capture_output=True,
		text=True,
		env=env,
		check=False,
	)


def _scrubbed_env() -> dict[str, str]:
	"""Return ``os.environ`` minus any LLM API keys.

	Mirrors the CI environment where no Anthropic credential exists.
	"""

	env = dict(os.environ)
	env.pop("ANTHROPIC_API_KEY", None)
	env.pop("CLAUDE_API_KEY", None)
	return env


def _git_available() -> bool:
	try:
		subprocess.run(
			["git", "--version"],
			capture_output=True,
			check=True,
		)
		return True
	except (FileNotFoundError, subprocess.CalledProcessError):
		return False


def _uv_available() -> bool:
	try:
		subprocess.run(
			["uv", "--version"],
			capture_output=True,
			check=True,
		)
		return True
	except (FileNotFoundError, subprocess.CalledProcessError):
		return False


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
@pytest.mark.skipif(not _uv_available(), reason="uv not on PATH")
@pytest.mark.parametrize("example", _EXAMPLES)
def test_polish_copy_commit_keeps_examples_tree_clean(example: str) -> None:
	"""``polish-copy --commit`` without an API key MUST NOT dirty examples/.

	Per ADR-002: ``flowforge polish-copy --commit`` is a committed-
	artifact gate. With no LLM available, the polish step is a no-op
	echo (canonical strings round-trip unchanged); the command MUST
	skip writing the sidecar so ``git status --porcelain`` stays clean.
	"""

	bundle = _EXAMPLES_DIR / example / "jtbd-bundle.json"
	assert bundle.exists(), f"missing example bundle: {bundle}"

	before = _examples_status(_REPO_ROOT)
	res = _run_polish_copy(bundle, env=_scrubbed_env())
	assert res.returncode == 0, (
		f"polish-copy --commit failed for {example}:\n"
		f"stdout={res.stdout}\nstderr={res.stderr}"
	)
	# The no-op echo path advertises itself in stdout; if a real LLM
	# ran here we'd want to know (test would be invalid in that env).
	assert "no-op echo" in res.stdout, (
		f"expected no-op echo path on no-API-key env, got: {res.stdout}"
	)
	after = _examples_status(_REPO_ROOT)
	assert before == after, (
		"polish-copy --commit dirtied the examples/ tree:\n"
		f"  before:\n{before}\n  after:\n{after}\n"
	)


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
@pytest.mark.parametrize("example", _EXAMPLES)
def test_no_committed_sidecar_drift(example: str) -> None:
	"""If a sidecar exists for *example*, it must already be committed.

	Catches the case where a developer ran ``polish-copy --commit``
	locally with an API key, produced an override file, but forgot to
	commit it. The CI gate is the safety net.
	"""

	bundle = _EXAMPLES_DIR / example / "jtbd-bundle.json"
	sidecar = bundle.with_name(bundle.name + ".overrides.json")
	if not sidecar.exists():
		# Common case in v0.3.0 W4b — no sidecars are checked in yet.
		# This branch keeps the test green pre-LLM-rollout.
		return
	res = subprocess.run(
		[
			"git",
			"ls-files",
			"--error-unmatch",
			str(sidecar.relative_to(_REPO_ROOT)),
		],
		cwd=_REPO_ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert res.returncode == 0, (
		f"sidecar {sidecar} exists on disk but is not committed — "
		"run `git add` and commit. ADR-002 makes the sidecar a tracked artifact."
	)
