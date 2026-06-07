"""``flowforge jtbd ai-draft`` — AI-assisted JTBD spec draft (E-14).

Generates a validated JtbdSpec from a free-text description using the
NlToJtbdGenerator pipeline with LlmProviderClaude. Runs JtbdLinter on
the draft before writing so warnings are surfaced to the author.

Exit codes:
- ``0`` — draft written (or printed) without linter errors.
- ``1`` — ANTHROPIC_API_KEY not set, generation failed, or linter returned errors.
- ``2`` — draft written but linter found warnings (advisory; does not block write).

Usage::

    flowforge jtbd ai-draft "A claimant files a loss report" --domain claims
    flowforge jtbd ai-draft "..." --out draft.json --commit
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from .jtbd_lint import _adapt_to_lint_bundle, _format_text


def register(app: typer.Typer) -> None:
	app.command(
		"ai-draft",
		help="Generate a JTBD spec draft from a free-text description using Claude AI.",
	)(jtbd_ai_draft_cmd)


def jtbd_ai_draft_cmd(
	description: Annotated[
		str,
		typer.Argument(help="Free-text description of the job-to-be-done."),
	],
	domain: Annotated[
		str | None,
		typer.Option("--domain", help="Domain hint added to the bundle project context."),
	] = None,
	out: Annotated[
		Path | None,
		typer.Option("--out", help="Output path for the generated JSON spec. Prints to stdout if omitted."),
	] = None,
	commit: Annotated[
		bool,
		typer.Option("--commit/--no-commit", help="Write the file even when linter warnings are present."),
	] = False,
	bundle_context: Annotated[
		Path | None,
		typer.Option("--bundle-context", help="Existing jtbd-bundle.json to supply shared roles/permissions to the LLM."),
	] = None,
) -> None:
	"""Generate a JTBD spec draft from DESCRIPTION using Claude AI.

	Requires ANTHROPIC_API_KEY in the environment. Fails closed without it.
	"""
	api_key = os.environ.get("ANTHROPIC_API_KEY")
	if not api_key:
		typer.echo(
			"error: ANTHROPIC_API_KEY is not set. "
			"Export it before running ai-draft.",
			err=True,
		)
		raise typer.Exit(1)

	# Lazy imports — keep CLI startup cost zero for non-AI commands.
	try:
		from flowforge_jtbd.ai.nl_to_jtbd import NlToJtbdGenerator
		from flowforge_jtbd.ports.llm_claude import LlmProviderClaude
	except ImportError as exc:
		typer.echo(
			f"error: cannot import AI modules: {exc}. "
			"Install flowforge-jtbd[claude] (pip install anthropic).",
			err=True,
		)
		raise typer.Exit(1) from exc

	ctx: dict[str, Any] | None = None
	if bundle_context is not None:
		if not bundle_context.exists():
			typer.echo(f"error: bundle-context not found: {bundle_context}", err=True)
			raise typer.Exit(1)
		try:
			import yaml  # type: ignore[import-untyped]
			raw_ctx = yaml.safe_load(bundle_context.read_text(encoding="utf-8"))
		except Exception:
			raw_ctx = json.loads(bundle_context.read_text(encoding="utf-8"))
		ctx = raw_ctx

	if domain and ctx is None:
		ctx = {"project": {"domain": domain}, "shared": {"roles": [], "permissions": []}}
	elif domain and ctx is not None:
		project = ctx.setdefault("project", {})
		project.setdefault("domain", domain)

	llm = LlmProviderClaude(api_key=api_key)
	generator = NlToJtbdGenerator(llm=llm)

	typer.echo("Generating JTBD draft…", err=True)
	try:
		result = asyncio.run(generator.generate(description, bundle_context=ctx))
	except Exception as exc:
		typer.echo(f"error: generation failed: {exc}", err=True)
		raise typer.Exit(1) from exc

	spec_dict = result.spec.model_dump(mode="json", exclude_none=True)

	# Surface compliance/sensitivity hints.
	if result.inferred_compliance:
		typer.echo(
			f"hint: inferred compliance regimes: {', '.join(result.inferred_compliance)}",
			err=True,
		)
	if result.inferred_sensitivity:
		typer.echo(
			f"hint: inferred data sensitivity: {', '.join(result.inferred_sensitivity)}",
			err=True,
		)
	if result.retried:
		typer.echo("note: generation succeeded after one retry.", err=True)

	# Run linter on a minimal synthetic bundle wrapping the draft.
	linter_exit = _lint_draft(spec_dict)

	spec_json = json.dumps(spec_dict, indent=2, sort_keys=True)

	if out is not None:
		should_write = linter_exit == 0 or commit
		if not should_write:
			typer.echo(
				"note: file not written because linter found errors "
				"(use --commit to force write despite warnings).",
				err=True,
			)
			raise typer.Exit(1)
		out.write_text(spec_json, encoding="utf-8")
		typer.echo(f"Draft written to {out}")
	else:
		typer.echo(spec_json)

	if linter_exit != 0:
		raise typer.Exit(linter_exit)


def _lint_draft(spec_dict: dict[str, Any]) -> int:
	"""Run the JTBD linter on the draft and print findings. Returns exit code."""
	from flowforge_jtbd.lint.linter import Linter

	# Wrap the single spec in a minimal bundle the linter can consume.
	jtbd_id = spec_dict.get("id") or "draft"
	raw_bundle: dict[str, Any] = {
		"project": {"name": "ai-draft"},
		"jtbds": [
			{
				**spec_dict,
				"jtbd_id": jtbd_id,
				"version": spec_dict.get("version", "1.0.0"),
			}
		],
		"shared": {"roles": [], "permissions": []},
	}
	adapted = _adapt_to_lint_bundle(raw_bundle)
	linter = Linter()
	try:
		report = linter.lint(adapted)
	except Exception as exc:  # noqa: BLE001
		typer.echo(f"warning: linter raised an exception: {exc}", err=True)
		return 0

	bundle_id = adapted.get("bundle_id") or "ai-draft"
	has_issues = bool(report.bundle_issues) or any(r.issues for r in report.results)
	if has_issues:
		typer.echo("--- linter findings on draft ---", err=True)
		typer.echo(_format_text(report, bundle_id), err=True)
		typer.echo("--- end linter findings ---", err=True)

	if not report.ok:
		return 1
	if report.warnings():
		return 2
	return 0


__all__ = ["jtbd_ai_draft_cmd", "register"]
