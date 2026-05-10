"""``flowforge pre-upgrade-check`` — F-7 mitigation for E-34 SK-01.

Audits the host for breaking-change readiness before bumping the framework
version that contains the SK-01 hardening.  Run as a CI/CD gate.

Today the only check is ``signing``; future audit-fix entries can register
new checks here without changing the public CLI shape.

W0 of v0.3.0 also wires an ``--alembic-chain`` subcheck (item 1 of
:doc:`docs/improvements`) that scans a directory of alembic revisions
for multi-head conditions: a deploy refuses to start when more than one
head exists, so the upgrade gate refuses to claim "ready" when we can
detect the fork in advance.

Reference: ``framework/docs/audit-fix-plan.md`` §2 risk F-7;
``framework/docs/audit-2026/SECURITY-NOTE.md`` E-34;
``framework/docs/v0.3.0-engineering-plan.md`` §5 Pre-mortem Scenario 3.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from .migration_safety import Severity, scan_directory


class _Check(str, Enum):
	"""Subjects supported by ``flowforge pre-upgrade-check <check>``."""

	signing = "signing"
	alembic_chain = "alembic-chain"
	pyproject = "pyproject"
	all = "all"


def _check_signing() -> tuple[bool, str]:
	"""Return ``(ok, message)`` for the SK-01 readiness check.

	Pass conditions (in order):

	1. ``FLOWFORGE_SIGNING_SECRET`` is set to a non-empty value — recommended.
	2. ``FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`` is set — bridge mode, OK for one
	   minor version with a loud warning.

	Otherwise the upgrade will fail at boot with ``RuntimeError("explicit
	secret required …")``.
	"""
	secret = os.environ.get("FLOWFORGE_SIGNING_SECRET")
	allow_insecure = os.environ.get("FLOWFORGE_ALLOW_INSECURE_DEFAULT")

	if secret:
		return (
			True,
			"signing: OK — FLOWFORGE_SIGNING_SECRET is set.",
		)
	if allow_insecure == "1":
		return (
			True,
			(
				"signing: WARN — FLOWFORGE_SIGNING_SECRET is unset; "
				"FLOWFORGE_ALLOW_INSECURE_DEFAULT=1 will keep the legacy "
				"hard-coded secret active for THIS minor version only.  "
				"Set FLOWFORGE_SIGNING_SECRET to a real secret before the "
				"next minor bump."
			),
		)
	return (
		False,
		(
			"signing: FAIL — neither FLOWFORGE_SIGNING_SECRET nor "
			"FLOWFORGE_ALLOW_INSECURE_DEFAULT=1 is set.  E-34 (SK-01) removed "
			"the hard-coded default; the upgraded process will refuse to "
			"start with RuntimeError.  Remediation: set "
			"FLOWFORGE_SIGNING_SECRET to a real secret in your secrets store, "
			"OR set FLOWFORGE_ALLOW_INSECURE_DEFAULT=1 for the deprecation "
			"window (loud-log warnings + counter alert)."
		),
	)


def _check_alembic_chain(versions_dir: Path | None) -> tuple[bool, str]:
	"""Return ``(ok, message)`` for the multi-head readiness check.

	Pass conditions:

	* The configured *versions_dir* is missing — nothing to check, treat
	  as a no-op pass with a hint message.
	* Exactly one alembic head present.

	Fail condition:

	* More than one head exists. Multi-head deploys fail with
	  ``alembic.util.exc.CommandError: Multiple heads`` and require an
	  explicit merge revision (``alembic merge heads``).
	"""

	# Default location chosen to match the generator output:
	# `backend/migrations/versions`. Hosts can override via
	# `FLOWFORGE_PRE_UPGRADE_VERSIONS_DIR`.
	if versions_dir is None:
		env_path = os.environ.get("FLOWFORGE_PRE_UPGRADE_VERSIONS_DIR")
		if env_path:
			versions_dir = Path(env_path)
		else:
			versions_dir = Path("backend/migrations/versions")

	if not versions_dir.is_dir():
		return (
			True,
			(
				f"alembic-chain: SKIP — `{versions_dir}` does not exist; "
				"nothing to scan. Pass `--versions-dir` or set "
				"FLOWFORGE_PRE_UPGRADE_VERSIONS_DIR to point at the host's "
				"alembic revisions if this is wrong."
			),
		)

	report = scan_directory(versions_dir)
	multi_head_findings = [f for f in report.findings if f.rule == "multi_head"]
	if not multi_head_findings:
		# Distinct ``branch_labels`` mean intentional parallel chains
		# (flowforge per-JTBD pattern); not a fork bug. Surface the
		# count so the operator knows the chain shape.
		distinct_branches = {
			m.branch_labels for m in report.migrations
			if m.branch_labels
		}
		if distinct_branches:
			return (
				True,
				(
					f"alembic-chain: OK — {len(distinct_branches)} parallel chain(s) "
					f"with distinct branch_labels across {len(report.migrations)} "
					f"revision(s) in `{versions_dir}`."
				),
			)
		return (
			True,
			(
				f"alembic-chain: OK — single head detected across "
				f"{len(report.migrations)} revision(s) in `{versions_dir}`."
			),
		)
	# Multi-head detected — emit one consolidated message.
	heads = sorted({f.location for f in multi_head_findings})
	return (
		False,
		(
			f"alembic-chain: FAIL — {len(multi_head_findings)} head(s) detected "
			f"in `{versions_dir}` ({', '.join(heads)}). Deploys will fail with "
			"`Multiple heads`. Remediation: run "
			"`alembic merge -m 'merge heads' <head_a> <head_b>` and commit the "
			"merge revision before upgrading."
		),
	)


def _check_pyproject(pyproject_path: Path | None) -> tuple[bool, str]:
	"""Return ``(ok, message)`` for the ``pyproject`` readiness check.

	v0.3.0 W4a / item 4 — per ADR-004, ``z3-solver`` is an opt-in
	runtime extra (``flowforge-cli[reachability]``) with a HARD version
	pin (``z3-solver==4.13.4.0``). Hosts that pin or unpin it elsewhere
	in their ``pyproject.toml`` will produce divergent reachability
	artefacts on regen because SAT counter-examples drift across z3
	versions. This subcheck warns when ``z3-solver`` appears outside
	the canonical ``[reachability]`` extra.

	Pass conditions (in order):

	1. The configured ``pyproject.toml`` is missing — nothing to scan,
	   treat as a no-op pass with a hint.
	2. ``z3-solver`` does not appear at all — host hasn't enabled
	   reachability; canonical state.
	3. ``z3-solver`` appears ONLY in the ``[project.optional-dependencies]
	   reachability`` block (or the host depends on
	   ``flowforge-cli[reachability]``) — opt-in path is correctly used.

	Warn condition:

	* ``z3-solver`` appears in any other section (top-level
	  ``dependencies``, ``[dependency-groups]`` other than via
	  ``flowforge-cli[reachability]``, ``[project.optional-dependencies]``
	  block other than ``reachability``). The message names the offending
	  section so the operator can move the dep into the canonical extra.
	"""

	# Default location matches `flowforge pre-upgrade-check` invocations
	# from a host's repo root.
	if pyproject_path is None:
		env_path = os.environ.get("FLOWFORGE_PRE_UPGRADE_PYPROJECT")
		if env_path:
			pyproject_path = Path(env_path)
		else:
			pyproject_path = Path("pyproject.toml")

	if not pyproject_path.is_file():
		return (
			True,
			(
				f"pyproject: SKIP — `{pyproject_path}` does not exist; "
				"nothing to scan. Pass `--pyproject-path` or set "
				"FLOWFORGE_PRE_UPGRADE_PYPROJECT to point at the host's "
				"pyproject.toml if this is wrong."
			),
		)

	try:
		text = pyproject_path.read_text(encoding="utf-8")
	except OSError as exc:
		return (
			False,
			f"pyproject: FAIL — cannot read `{pyproject_path}`: {exc}",
		)

	# Cheap line-by-line scan rather than a full TOML parse: we want to
	# locate every section that mentions ``z3-solver`` and decide whether
	# the section is the canonical ``[project.optional-dependencies]
	# reachability`` block. tomllib would lose the section context cheaply
	# but tracking ``[<section>]`` headings by line is enough — pyproject
	# files are small and we only care about presence/absence.
	current_section: str = ""
	current_subsection: str = ""
	offending_sections: list[str] = []
	saw_canonical_extra: bool = False
	saw_flowforge_cli_extra: bool = False

	for raw_line in text.splitlines():
		line = raw_line.strip()
		if line.startswith("[") and line.endswith("]"):
			# New TOML section header — reset the subsection tracker.
			current_section = line.strip("[]").strip()
			current_subsection = ""
			continue
		if not line or line.startswith("#"):
			continue
		# Inline-table sub-entries inside ``[project.optional-dependencies]``
		# or ``[dependency-groups]`` look like ``reachability = [`` opening
		# the inline list. Track the nearest ``key = [`` to know which
		# extra/group the subsequent entries belong to.
		if "=" in line and (line.endswith("[") or line.rstrip().endswith("[")):
			key = line.split("=", 1)[0].strip()
			current_subsection = key
			continue
		if line == "]":
			current_subsection = ""
			continue
		# Match ``flowforge-cli[reachability]`` references — the canonical
		# transitive way to pull z3 in via the extra.
		if "flowforge-cli[reachability]" in line:
			saw_flowforge_cli_extra = True
		# z3-solver mention — classify by current section + subsection.
		if "z3-solver" in line:
			if (
				current_section == "project.optional-dependencies"
				and current_subsection == "reachability"
			):
				saw_canonical_extra = True
				continue
			# Anything else is an offending location.
			label = current_section
			if current_subsection:
				label = f"{current_section}.{current_subsection}"
			offending_sections.append(label or "<top-level>")

	if not offending_sections and not saw_canonical_extra and not saw_flowforge_cli_extra:
		return (
			True,
			(
				f"pyproject: OK — `{pyproject_path}` does not reference z3-solver. "
				"The reachability extra is opt-in; install with "
				"`pip install 'flowforge-cli[reachability]'` to enable per-JTBD "
				"symbolic reachability analysis."
			),
		)
	if not offending_sections:
		return (
			True,
			(
				f"pyproject: OK — `{pyproject_path}` references z3-solver only via the "
				"canonical opt-in path "
				"(`[project.optional-dependencies] reachability` or "
				"`flowforge-cli[reachability]`)."
			),
		)
	# Deduplicate while preserving discovery order.
	seen: set[str] = set()
	dedup: list[str] = []
	for label in offending_sections:
		if label in seen:
			continue
		seen.add(label)
		dedup.append(label)
	return (
		False,
		(
			f"pyproject: WARN — `{pyproject_path}` references z3-solver in "
			f"{len(dedup)} non-canonical location(s): {', '.join(dedup)}. "
			"Per ADR-004 z3-solver MUST live in "
			"`[project.optional-dependencies] reachability` (hard-pinned to "
			"`==4.13.4.0`) or be pulled transitively via "
			"`flowforge-cli[reachability]`. Range-pinned or unpinned z3 produces "
			"divergent SAT counter-examples and breaks byte-identical regen."
		),
	)


_CHECKS = {
	_Check.signing: lambda *, versions_dir=None, pyproject_path=None: _check_signing(),
	_Check.alembic_chain: lambda *, versions_dir=None, pyproject_path=None: _check_alembic_chain(versions_dir),
	_Check.pyproject: lambda *, versions_dir=None, pyproject_path=None: _check_pyproject(pyproject_path),
}


def pre_upgrade_check_cmd(
	check: Annotated[
		_Check,
		typer.Argument(help="Specific check to run, or ``all`` for every registered check."),
	] = _Check.all,
	versions_dir: Annotated[
		Path | None,
		typer.Option(
			"--versions-dir",
			help=(
				"Directory of alembic revision files to scan for multi-head conditions. "
				"Defaults to `backend/migrations/versions` or the value of "
				"FLOWFORGE_PRE_UPGRADE_VERSIONS_DIR if set."
			),
			file_okay=False,
			dir_okay=True,
		),
	] = None,
	alembic_chain: Annotated[
		bool,
		typer.Option(
			"--alembic-chain/--no-alembic-chain",
			help=(
				"Force-include the alembic-chain subcheck even when running a "
				"single-check invocation. Equivalent to `pre-upgrade-check alembic-chain`."
			),
		),
	] = False,
	pyproject_path: Annotated[
		Path | None,
		typer.Option(
			"--pyproject-path",
			help=(
				"Path to the host's pyproject.toml. Defaults to `pyproject.toml` "
				"in the current working directory or the value of "
				"FLOWFORGE_PRE_UPGRADE_PYPROJECT if set. Used by the "
				"`pyproject` subcheck to flag non-canonical z3-solver "
				"declarations (per ADR-004)."
			),
			file_okay=True,
			dir_okay=False,
		),
	] = None,
	check_pyproject: Annotated[
		bool,
		typer.Option(
			"--check-pyproject/--no-check-pyproject",
			help=(
				"Force-include the pyproject subcheck even when running a "
				"single-check invocation. Equivalent to `pre-upgrade-check pyproject`. "
				"v0.3.0 W4a / item 4 — flags z3-solver references outside the "
				"canonical `[project.optional-dependencies] reachability` extra."
			),
		),
	] = False,
) -> None:
	"""Run the requested pre-upgrade audit-2026 check(s) and exit non-zero on failure."""
	if check == _Check.all:
		subjects = [c for c in _CHECKS]
	else:
		subjects = [check]
	# `--alembic-chain` flag forces inclusion when not in `all` mode.
	if alembic_chain and _Check.alembic_chain not in subjects:
		subjects.append(_Check.alembic_chain)
	# `--check-pyproject` flag forces inclusion when not in `all` mode.
	if check_pyproject and _Check.pyproject not in subjects:
		subjects.append(_Check.pyproject)

	failed = 0
	for subject in subjects:
		fn = _CHECKS[subject]
		ok, msg = fn(versions_dir=versions_dir, pyproject_path=pyproject_path)
		typer.echo(msg)
		if not ok:
			failed += 1

	if failed:
		typer.echo(
			f"\npre-upgrade-check: {failed} check(s) failed — see SECURITY-NOTE.md "
			"or `flowforge migration-safety` output for remediation.",
			err=True,
		)
		raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
	"""Mount ``flowforge pre-upgrade-check`` on the root app."""
	app.command(
		"pre-upgrade-check",
		help=(
			"Audit the host for audit-2026 breaking-change readiness "
			"(F-7 mitigation; see SECURITY-NOTE.md). W0/v0.3.0 adds "
			"`alembic-chain` for multi-head detection; W4a/v0.3.0 adds "
			"`pyproject` for non-canonical z3-solver references "
			"(per ADR-004)."
		),
	)(pre_upgrade_check_cmd)


# Re-export so tests / other modules can import the severity enum without
# pulling in the migration_safety command surface.
__all__ = ["pre_upgrade_check_cmd", "register", "Severity"]
