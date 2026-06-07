"""``flowforge jtbd compliance-lint`` — compliance linter for JTBD bundles (E-23).

Runs the ComplianceLinterPack (sensitivity→regime and regime→required-job
rules) against a JTBD bundle file, optionally filtered to a single regime.

Exit codes:
- ``0`` — no issues (or issues are advisory with ``--no-strict``).
- ``1`` — errors found, or ``--strict`` with warnings.

Usage::

    flowforge jtbd compliance-lint path/to/jtbd-bundle.json
    flowforge jtbd compliance-lint path/to/jtbd-bundle.json --regime GDPR
    flowforge jtbd compliance-lint path/to/jtbd-bundle.json --regime HIPAA --strict
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from .._io import load_structured
from .jtbd_lint import _adapt_to_lint_bundle, _severity_prefix
from flowforge_jtbd.lint.results import Issue, LintReport


_VALID_REGIMES = frozenset({"GDPR", "HIPAA", "SOX", "PCI-DSS", "ISO27001", "SOC2", "NIST-800-53", "CCPA"})


def register(app: typer.Typer) -> None:
	app.command(
		"compliance-lint",
		help="Lint a JTBD bundle for compliance regime coverage (sensitivity→regime, regime→required-job).",
	)(jtbd_compliance_lint_cmd)


def jtbd_compliance_lint_cmd(
	bundle_path: Annotated[
		Path,
		typer.Argument(help="JTBD bundle JSON/YAML file to check."),
	],
	regime: Annotated[
		str | None,
		typer.Option(
			"--regime",
			help=f"Filter to a single compliance regime. One of: {', '.join(sorted(_VALID_REGIMES))}.",
		),
	] = None,
	strict: Annotated[
		bool,
		typer.Option("--strict/--no-strict", help="Treat warnings as errors (exit 1)."),
	] = False,
	fmt: Annotated[
		str,
		typer.Option("--format", help="Output format: text or json."),
	] = "text",
) -> None:
	"""Run compliance lint rules on BUNDLE_PATH.

	Two rules run:
	  - ``sensitivity_implies_regime``: specs that declare PHI/PCI/PII must
	    declare the corresponding compliance regime.
	  - ``compliance_missing_required_job``: regimes that require specific
	    JTBD job ids must have those ids present in the bundle.
	"""
	if not bundle_path.exists():
		typer.echo(f"error: bundle not found: {bundle_path}", err=True)
		raise typer.Exit(1)

	if regime is not None and regime not in _VALID_REGIMES:
		typer.echo(
			f"error: unknown regime '{regime}'. "
			f"Valid values: {', '.join(sorted(_VALID_REGIMES))}",
			err=True,
		)
		raise typer.Exit(1)

	from flowforge_jtbd.lint.actors import ActorConsistencyAnalyzer
	from flowforge_jtbd.lint.compliance import ComplianceLinterPack
	from flowforge_jtbd.lint.lifecycle import LifecycleAnalyzer
	from flowforge_jtbd.lint.linter import Linter
	from flowforge_jtbd.lint.registry import RuleRegistry
	from flowforge_jtbd.spec import JtbdBundle, JtbdLintSpec

	raw: dict[str, Any] = load_structured(bundle_path)
	adapted = _adapt_to_lint_bundle(raw)
	bundle_id: str = adapted.get("bundle_id") or "unknown"

	# Use null-pass stub analyzers so that lifecycle/actor rules don't
	# fire — this command is scoped to compliance rules only.
	class _NullLifecycle(LifecycleAnalyzer):
		def analyze(self, bundle: JtbdBundle, spec: JtbdLintSpec) -> list[Issue]:
			return []

	class _NullActors(ActorConsistencyAnalyzer):
		def analyze(self, bundle: JtbdBundle) -> dict[str, list[Issue]]:
			return {}

	# Run linter with only the compliance rule pack.
	linter = Linter(
		lifecycle=_NullLifecycle(),
		actors=_NullActors(),
		registry=RuleRegistry([ComplianceLinterPack()]),
	)
	try:
		report = linter.lint(adapted)
	except Exception as exc:  # noqa: BLE001
		typer.echo(f"error: compliance linter raised an exception: {exc}", err=True)
		raise typer.Exit(1) from exc

	# Filter report to the requested regime if one was given.
	if regime:
		report = _filter_regime(report, regime)

	if fmt == "json":
		typer.echo(_format_json(report, bundle_id))
	else:
		typer.echo(_format_text(report, bundle_id))

	has_errors = not report.ok
	has_warnings = bool(report.warnings())

	if has_errors:
		raise typer.Exit(1)
	if strict and has_warnings:
		raise typer.Exit(1)


def _filter_regime(report: LintReport, regime: str) -> LintReport:
	"""Return a copy of *report* keeping only issues that mention *regime*."""
	def _issue_matches(issue: Issue) -> bool:
		return regime.upper() in issue.message.upper()

	from flowforge_jtbd.lint.results import JtbdResult

	new_bundle_issues = [i for i in report.bundle_issues if _issue_matches(i)]
	new_results = [
		JtbdResult(
			jtbd_id=r.jtbd_id,
			version=r.version,
			issues=[i for i in r.issues if _issue_matches(i)],
		)
		for r in report.results
	]
	ok = (
		not any(i.severity == "error" for i in new_bundle_issues)
		and not any(
			i.severity == "error"
			for r in new_results
			for i in r.issues
		)
	)
	return LintReport(
		ok=ok,
		results=new_results,
		bundle_issues=new_bundle_issues,
		topological_order=report.topological_order,
	)


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
		lines.append("  ok — no compliance issues found")

	status = "ok" if report.ok else "FAIL"
	lines.append(f"result: {status}")
	return "\n".join(lines)


def _format_json(report: LintReport, bundle_id: str) -> str:
	return json.dumps(
		{
			"bundle_id": bundle_id,
			"ok": report.ok,
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


__all__ = ["jtbd_compliance_lint_cmd", "register"]
