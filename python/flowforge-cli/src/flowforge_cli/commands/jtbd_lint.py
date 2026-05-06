"""``flowforge jtbd lint`` — semantic linter for JTBD bundles (E-9).

Runs the lifecycle, dependency, and actor-consistency analyzers from
:mod:`flowforge_jtbd.lint` against a JTBD bundle file and reports
findings with severity (error / warning / info).

Exit codes:
- ``0`` — bundle is clean (no errors; warnings don't block by default).
- ``1`` — one or more errors found, or ``--strict`` used with warnings.

Examples::

    # Lint the default bundle file:
    flowforge jtbd lint

    # Lint a specific bundle:
    flowforge jtbd lint --bundle path/to/jtbd-bundle.json

    # Treat warnings as errors (CI strict mode):
    flowforge jtbd lint --bundle jtbd-bundle.json --strict

    # Machine-readable output:
    flowforge jtbd lint --bundle jtbd-bundle.json --format json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from .._io import load_structured
from flowforge_jtbd.lint.linter import Linter
from flowforge_jtbd.lint.results import Issue, LintReport


# ---------------------------------------------------------------------------
# Bundle adapter
# ---------------------------------------------------------------------------


def _adapt_to_lint_bundle(raw: dict[str, Any]) -> dict[str, Any]:
	"""Convert a raw JTBD bundle dict to the shape JtbdBundle.model_validate expects.

	The on-disk bundle uses ``id`` per JTBD and ``project.name`` as the
	bundle identifier; the lint model uses ``jtbd_id`` and ``bundle_id``.
	``version`` defaults to ``"1.0.0"`` when absent (pre-E-1 bundles).

	``bundle.shared.roles`` may be either a list of role names (the
	flowforge-cli normalize.py shape) or a dict keyed by role name. Both
	forms are translated to the lint side's ``shared_roles: dict[str,
	RoleDef]``; missing tier defaults to ``0``.
	"""
	project = raw.get("project") or {}
	bundle_id = project.get("name") or "unknown"

	adapted_jtbds: list[dict[str, Any]] = []
	for jtbd in raw.get("jtbds", []) or []:
		entry = dict(jtbd)
		if "jtbd_id" not in entry:
			entry["jtbd_id"] = entry.get("id", "unknown")
		if not entry.get("version"):
			entry["version"] = "1.0.0"
		adapted_jtbds.append(entry)

	shared_roles = _adapt_shared_roles(raw.get("shared") or {})

	return {
		"bundle_id": bundle_id,
		"jtbds": adapted_jtbds,
		"shared_roles": shared_roles,
	}


def _adapt_shared_roles(shared: dict[str, Any]) -> dict[str, dict[str, Any]]:
	"""Normalise ``shared.roles`` into the lint side's dict shape."""
	roles = shared.get("roles")
	if not roles:
		return {}
	if isinstance(roles, list):
		# List of role names → minimal RoleDefs.
		out: dict[str, dict[str, Any]] = {}
		for name in roles:
			if isinstance(name, str) and name:
				out[name] = {"name": name}
			elif isinstance(name, dict) and name.get("name"):
				out[name["name"]] = dict(name)
		return out
	if isinstance(roles, dict):
		# Dict keyed by role name. Each value is a RoleDef-shaped mapping
		# (or a bare tier int for terse hosts — not common but cheap to
		# accept).
		out2: dict[str, dict[str, Any]] = {}
		for name, value in roles.items():
			if isinstance(value, dict):
				entry = dict(value)
				entry.setdefault("name", name)
				out2[name] = entry
			elif isinstance(value, int):
				out2[name] = {"name": name, "default_tier": value}
		return out2
	return {}


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _severity_prefix(issue: Issue) -> str:
	return {"error": "ERR", "warning": "WRN", "info": "INF"}.get(issue.severity, "???")


def _format_text(report: LintReport, bundle_id: str) -> str:
	lines: list[str] = [f"bundle: {bundle_id}"]
	has_findings = False

	for issue in report.bundle_issues:
		lines.append(f"  [{_severity_prefix(issue)}] bundle — {issue.rule}: {issue.message}")
		if issue.fixhint:
			lines.append(f"        fixhint: {issue.fixhint}")
		has_findings = True

	for result in report.results:
		for issue in result.issues:
			lines.append(
				f"  [{_severity_prefix(issue)}] {result.jtbd_id} — {issue.rule}: {issue.message}"
			)
			if issue.fixhint:
				lines.append(f"        fixhint: {issue.fixhint}")
			has_findings = True

	if not has_findings:
		lines.append("  ok — no issues found")

	if report.topological_order:
		lines.append(f"  topological order: {' → '.join(report.topological_order)}")

	status = "ok" if report.ok else "FAIL"
	lines.append(f"result: {status}")
	return "\n".join(lines)


def _format_json(report: LintReport, bundle_id: str) -> str:
	return json.dumps(
		{
			"bundle_id": bundle_id,
			"ok": report.ok,
			"topological_order": report.topological_order,
			"bundle_issues": [i.model_dump() for i in report.bundle_issues],
			"results": [
				{
					"jtbd_id": r.jtbd_id,
					"version": r.version,
					"issues": [i.model_dump() for i in r.issues],
				}
				for r in report.results
			],
		},
		indent=2,
		sort_keys=True,
	)


# ---------------------------------------------------------------------------
# Default bundle search paths
# ---------------------------------------------------------------------------


_DEFAULT_CANDIDATES = (
	"jtbd-bundle.json",
	"jtbd_bundle.json",
	"workflows/jtbd_bundle.json",
	"workflows/jtbd-bundle.json",
)


def _find_default_bundle() -> Path | None:
	for name in _DEFAULT_CANDIDATES:
		p = Path(name)
		if p.is_file():
			return p
	return None


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
	app.command(
		"lint",
		help="Lint a JTBD bundle for lifecycle, dependency, and actor-consistency issues.",
	)(jtbd_lint_cmd)


def jtbd_lint_cmd(
	bundle: Annotated[
		Path | None,
		typer.Option(
			"--bundle",
			dir_okay=False,
			help="JTBD bundle JSON/YAML. Auto-detected if omitted.",
		),
	] = None,
	strict: Annotated[
		bool,
		typer.Option("--strict/--no-strict", help="Treat warnings as errors."),
	] = False,
	warn_only: Annotated[
		bool,
		typer.Option("--warn-only", help="Never exit non-zero (advisory mode)."),
	] = False,
	fmt: Annotated[
		str,
		typer.Option("--format", help="Output format: text or json."),
	] = "text",
) -> None:
	"""Lint BUNDLE for semantic errors using the E-4 analyzer suite."""

	if bundle is None:
		bundle = _find_default_bundle()
		if bundle is None:
			typer.echo(
				"error: no bundle file found; pass --bundle or place jtbd-bundle.json in the "
				"current directory.",
				err=True,
			)
			raise typer.Exit(1)

	if not bundle.exists():
		typer.echo(f"error: bundle not found: {bundle}", err=True)
		raise typer.Exit(1)

	raw = load_structured(bundle)
	adapted = _adapt_to_lint_bundle(raw)
	bundle_id: str = adapted.get("bundle_id") or "unknown"

	linter = Linter()
	try:
		report = linter.lint(adapted)
	except Exception as exc:  # noqa: BLE001
		typer.echo(f"error: linter raised an exception: {exc}", err=True)
		raise typer.Exit(1) from exc

	if fmt == "json":
		typer.echo(_format_json(report, bundle_id))
	else:
		typer.echo(_format_text(report, bundle_id))

	if warn_only:
		return

	if not report.ok:
		raise typer.Exit(1)
	if strict and (report.warnings()):
		raise typer.Exit(1)
