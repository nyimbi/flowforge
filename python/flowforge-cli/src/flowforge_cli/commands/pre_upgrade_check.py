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


_CHECKS = {
	_Check.signing: lambda *, versions_dir=None: _check_signing(),
	_Check.alembic_chain: lambda *, versions_dir=None: _check_alembic_chain(versions_dir),
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
) -> None:
	"""Run the requested pre-upgrade audit-2026 check(s) and exit non-zero on failure."""
	if check == _Check.all:
		subjects = [c for c in _CHECKS]
	else:
		subjects = [check]
	# `--alembic-chain` flag forces inclusion when not in `all` mode.
	if alembic_chain and _Check.alembic_chain not in subjects:
		subjects.append(_Check.alembic_chain)

	failed = 0
	for subject in subjects:
		fn = _CHECKS[subject]
		ok, msg = fn(versions_dir=versions_dir)
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
			"`alembic-chain` for multi-head detection."
		),
	)(pre_upgrade_check_cmd)


# Re-export so tests / other modules can import the severity enum without
# pulling in the migration_safety command surface.
__all__ = ["pre_upgrade_check_cmd", "register", "Severity"]
