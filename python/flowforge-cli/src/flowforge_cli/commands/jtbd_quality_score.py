"""``flowforge jtbd quality-score`` — JTBD bundle quality scorer (E-16).

Runs the deterministic QualityScorer rubric against every JTBD in a
bundle and prints per-spec 0-100 scores with dimension breakdowns.

Exit codes:
- ``0`` — all specs pass (score ≥ 60 by default).
- ``1`` — one or more specs below the quality threshold.

Usage::

    flowforge jtbd quality-score path/to/jtbd-bundle.json
    flowforge jtbd quality-score path/to/jtbd-bundle.json --json
    flowforge jtbd quality-score path/to/jtbd-bundle.json --threshold 70
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from .._io import load_structured


def register(app: typer.Typer) -> None:
	app.command(
		"quality-score",
		help="Score every JTBD in a bundle on a 0-100 quality rubric.",
	)(jtbd_quality_score_cmd)


def jtbd_quality_score_cmd(
	bundle_path: Annotated[
		Path,
		typer.Argument(help="JTBD bundle JSON/YAML file to score."),
	],
	as_json: Annotated[
		bool,
		typer.Option("--json", is_flag=True, help="Emit machine-readable JSON output."),
	] = False,
	threshold: Annotated[
		int,
		typer.Option("--threshold", help="Score below which a spec is flagged low-quality (default 60)."),
	] = 60,
) -> None:
	"""Score every JTBD in BUNDLE_PATH using the E-16 quality rubric.

	Prints per-spec scores with dimension breakdowns. Exits 1 if any
	spec falls below the quality threshold.
	"""
	if not bundle_path.exists():
		typer.echo(f"error: bundle not found: {bundle_path}", err=True)
		raise typer.Exit(1)

	from flowforge_jtbd.ai.quality import QualityScorer

	raw: dict[str, Any] = load_structured(bundle_path)
	jtbds: list[dict[str, Any]] = raw.get("jtbds") or []

	if not jtbds:
		typer.echo("warning: no JTBDs found in bundle", err=True)
		raise typer.Exit(0)

	scorer = QualityScorer(low_quality_threshold=threshold)
	reports = []
	for spec in jtbds:
		report = scorer.score_sync(spec)
		reports.append(report)

	any_low = any(r.low_quality for r in reports)

	if as_json:
		output = {
			"bundle": str(bundle_path),
			"threshold": threshold,
			"all_pass": not any_low,
			"jtbds": [
				{
					"id": r.jtbd_id,
					"score": r.score,
					"low_quality": r.low_quality,
					"dimensions": [
						{
							"name": d.name,
							"score": d.score,
							"findings": d.findings,
						}
						for d in r.dimensions
					],
				}
				for r in reports
			],
		}
		typer.echo(json.dumps(output, indent=2))
	else:
		typer.echo(f"bundle: {bundle_path}")
		typer.echo(f"threshold: {threshold}")
		typer.echo("")
		for r in reports:
			flag = " [LOW]" if r.low_quality else ""
			typer.echo(f"  {r.jtbd_id}: {r.score}/100{flag}")
			for d in r.dimensions:
				dim_flag = " [LOW]" if d.score < threshold else ""
				typer.echo(f"    {d.name}: {d.score}/100{dim_flag}")
				for finding in d.findings:
					typer.echo(f"      · {finding}")
			typer.echo("")
		status = "FAIL" if any_low else "ok"
		typer.echo(f"result: {status}")

	if any_low:
		raise typer.Exit(1)


__all__ = ["jtbd_quality_score_cmd", "register"]
