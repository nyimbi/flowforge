"""``flowforge lint-jtbd`` - lint one JTBD JSON file."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.panel import Panel
from rich.table import Table

from .._io import load_structured
from .._ux import console, error, success
from .jtbd_lint import _adapt_to_lint_bundle, _format_json


def register(app: typer.Typer) -> None:
	app.command(
		"lint-jtbd",
		help="Lint a single JTBD JSON/YAML file and show a rich validation report.",
		epilog="[bold]--example[/]: flowforge lint-jtbd claim_intake.json --strict",
	)(lint_jtbd_cmd)


def lint_jtbd_cmd(
	file: Annotated[
		Path,
		typer.Argument(
			exists=True,
			dir_okay=False,
			help="Single JTBD JSON/YAML file to lint (Path, required).",
		),
	],
	shared_role: Annotated[
		list[str] | None,
		typer.Option(
			"--shared-role",
			help="Role name to treat as declared in shared.roles; repeatable (str, default: none).",
		),
	] = None,
	bundle_name: Annotated[
		str,
		typer.Option(
			"--bundle-name",
			help="Synthetic bundle name used in the linter report (str, default: single-jtbd).",
		),
	] = "single-jtbd",
	strict: Annotated[
		bool,
		typer.Option(
			"--strict/--no-strict",
			help="Treat warnings as blocking failures (bool, default: false).",
		),
	] = False,
	as_json: Annotated[
		bool,
		typer.Option(
			"--json",
			help="Emit machine-readable JSON instead of a Rich report (bool, default: false).",
		),
	] = False,
) -> None:
	"""Lint one JTBD file with the same semantic analyzer used by ``jtbd lint``."""

	try:
		raw = load_structured(file)
	except Exception as exc:
		error(
			"Could not read the JTBD file.",
			why=f"{type(exc).__name__}: {exc}",
			next_step="Fix the JSON/YAML syntax and retry lint-jtbd.",
		)
		raise typer.Exit(1) from exc

	try:
		spec = _extract_single_jtbd(raw)
	except ValueError as exc:
		error(
			"The input is not a single JTBD spec.",
			why=str(exc),
			next_step="Pass one JTBD object, or use flowforge jtbd lint for a bundle.",
		)
		raise typer.Exit(1) from exc

	bundle = {
		"project": {"name": bundle_name},
		"shared": {"roles": list(shared_role or [])},
		"jtbds": [spec],
	}
	adapted = _adapt_to_lint_bundle(bundle)
	from flowforge_jtbd.lint.linter import Linter

	try:
		report = Linter().lint(adapted)
	except Exception as exc:  # noqa: BLE001
		error(
			"The JTBD linter could not complete.",
			why=f"{type(exc).__name__}: {exc}",
			next_step="Check that the JTBD fields match the Flowforge JTBD schema.",
		)
		raise typer.Exit(1) from exc

	if as_json:
		console.print(_format_json(report, bundle_name), markup=False, soft_wrap=True)
	else:
		_print_report(file, report)

	has_errors = not report.ok
	has_warnings = bool(report.warnings())
	if has_errors:
		raise typer.Exit(1)
	if strict and has_warnings:
		raise typer.Exit(1)
	if has_warnings:
		raise typer.Exit(2)


def _extract_single_jtbd(raw: dict[str, Any]) -> dict[str, Any]:
	if isinstance(raw.get("jtbds"), list):
		jtbds = raw["jtbds"]
		if len(jtbds) != 1:
			raise ValueError(f"bundle contains {len(jtbds)} JTBDs, not exactly one")
		item = jtbds[0]
		if not isinstance(item, dict):
			raise ValueError("bundle jtbds[0] must be an object")
		return item
	if "id" in raw or "jtbd_id" in raw:
		return raw
	raise ValueError("expected an object with id or jtbd_id")


def _print_report(file: Path, report: Any) -> None:
	error_count = 0
	warning_count = 0
	info_count = 0
	rows: list[tuple[str, str, str, str, str]] = []
	for issue in report.bundle_issues:
		rows.append((issue.severity, "bundle", issue.rule, issue.message, issue.fixhint or "Review the bundle-level rule."))
	for result in report.results:
		for issue in result.issues:
			rows.append(
				(
					issue.severity,
					result.jtbd_id,
					issue.rule,
					issue.message,
					issue.fixhint or "Update the JTBD and run lint-jtbd again.",
				)
			)
	for severity, *_ in rows:
		if severity == "error":
			error_count += 1
		elif severity == "warning":
			warning_count += 1
		else:
			info_count += 1

	status = "PASS" if report.ok else "FAIL"
	border = "green" if report.ok else "red"
	console.print(
		Panel(
			f"[bold]File[/]: {file}\n"
			f"[bold]Result[/]: {status}\n"
			f"[bold]Findings[/]: {error_count} errors, {warning_count} warnings, {info_count} info",
			title="JTBD Validation Report",
			border_style=border,
		)
	)
	if rows:
		table = Table(title="Findings", show_header=True, header_style="bold")
		table.add_column("Severity")
		table.add_column("JTBD")
		table.add_column("Why")
		table.add_column("What went wrong")
		table.add_column("What to do next")
		for severity, jtbd_id, rule, message, fixhint in rows:
			style = {"error": "red", "warning": "yellow", "info": "cyan"}.get(severity, "")
			table.add_row(severity.upper(), jtbd_id, rule, message, fixhint, style=style)
		console.print(table)
		if error_count == 0 and warning_count == 0:
			success("JTBD file passed validation")
	else:
		success("JTBD file passed validation")
