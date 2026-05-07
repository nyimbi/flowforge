"""``flowforge pre-upgrade-check`` — F-7 mitigation for E-34 SK-01.

Audits the host for breaking-change readiness before bumping the framework
version that contains the SK-01 hardening.  Run as a CI/CD gate.

Today the only check is ``signing``; future audit-fix entries can register
new checks here without changing the public CLI shape.

Reference: ``framework/docs/audit-fix-plan.md`` §2 risk F-7;
``framework/docs/audit-2026/SECURITY-NOTE.md`` E-34.
"""

from __future__ import annotations

import os
from enum import Enum

import typer


class _Check(str, Enum):
	"""Subjects supported by ``flowforge pre-upgrade-check <check>``."""

	signing = "signing"
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


_CHECKS = {
	_Check.signing: _check_signing,
}


def pre_upgrade_check_cmd(
	check: _Check = typer.Argument(
		_Check.all,
		help="Specific check to run, or ``all`` for every registered check.",
	),
) -> None:
	"""Run the requested pre-upgrade audit-2026 check(s) and exit non-zero on failure."""
	if check == _Check.all:
		subjects = [c for c in _CHECKS]
	else:
		subjects = [check]

	failed = 0
	for subject in subjects:
		fn = _CHECKS[subject]
		ok, msg = fn()
		typer.echo(msg)
		if not ok:
			failed += 1

	if failed:
		typer.echo(
			f"\npre-upgrade-check: {failed} check(s) failed — see SECURITY-NOTE.md "
			"for remediation.",
			err=True,
		)
		raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
	"""Mount ``flowforge pre-upgrade-check`` on the root app."""
	app.command(
		"pre-upgrade-check",
		help=(
			"Audit the host for audit-2026 breaking-change readiness "
			"(F-7 mitigation; see SECURITY-NOTE.md)."
		),
	)(pre_upgrade_check_cmd)
