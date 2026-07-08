"""``flowforge new-workflow`` - scaffold a minimal workflow_def.json."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .._io import write_json
from .._ux import console, error, success


_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def register(app: typer.Typer) -> None:
	app.command(
		"new-workflow",
		help="Scaffold a minimal workflow_def.json for a new workflow.",
		epilog="[bold]--example[/]: flowforge new-workflow claim-intake --subject-kind claim",
	)(new_workflow_cmd)


def new_workflow_cmd(
	name: Annotated[
		str,
		typer.Argument(
			help="Workflow name/key to scaffold (str, required; letters, digits, hyphen, underscore).",
		),
	],
	out: Annotated[
		Path | None,
		typer.Option(
			"--out",
			"-o",
			help="Output file path (Path, default: workflows/<name>/workflow_def.json).",
		),
	] = None,
	subject_kind: Annotated[
		str,
		typer.Option(
			"--subject-kind",
			help="Subject kind stored in the workflow definition (str, default: subject).",
		),
	] = "subject",
	force: Annotated[
		bool,
		typer.Option(
			"--force",
			help="Overwrite an existing workflow_def.json (bool, default: false).",
		),
	] = False,
) -> None:
	"""Create a minimal workflow definition file."""

	if not _SAFE_NAME.fullmatch(name):
		error(
			"Workflow name is invalid.",
			why="Names must start with a letter and contain only letters, digits, hyphen, or underscore.",
			next_step="Use a name like claim-intake or claim_intake.",
		)
		raise typer.Exit(1)

	key = name.replace("-", "_")
	dst = out or Path("workflows") / key / "workflow_def.json"
	if dst.exists() and not force:
		error(
			"Workflow file already exists.",
			why=f"{dst} would be overwritten.",
			next_step="Pass --force to replace it, or choose a different --out path.",
		)
		raise typer.Exit(1)

	workflow = _workflow_def(key, subject_kind=subject_kind)
	with Progress(
		SpinnerColumn(),
		TextColumn("[progress.description]{task.description}"),
		BarColumn(),
		console=console,
		transient=True,
	) as progress:
		task = progress.add_task("Creating workflow scaffold", total=3)
		dst.parent.mkdir(parents=True, exist_ok=True)
		progress.advance(task)
		write_json(dst, workflow)
		progress.advance(task)
		progress.update(task, description="Preparing summary")
		progress.advance(task)

	console.print(
		Panel(
			f"[bold]Workflow[/]: {key}\n[bold]File[/]: {dst}\n[bold]States[/]: 3\n[bold]Transitions[/]: 2",
			title="Workflow Scaffold",
			border_style="green",
		)
	)
	table = Table(title="Created Definition", show_header=True, header_style="bold")
	table.add_column("Field")
	table.add_column("Value")
	for field, value in (
		("key", key),
		("version", workflow["version"]),
		("subject_kind", workflow["subject_kind"]),
		("initial_state", workflow["initial_state"]),
	):
		table.add_row(field, str(value))
	console.print(table)
	success(f"created {dst}")


def _workflow_def(key: str, *, subject_kind: str) -> dict[str, Any]:
	return {
		"key": key,
		"version": "0.1.0",
		"subject_kind": subject_kind,
		"initial_state": "draft",
		"metadata": {"generated_by": "flowforge new-workflow"},
		"states": [
			{"name": "draft", "kind": "manual_review", "swimlane": "author"},
			{"name": "review", "kind": "manual_review", "swimlane": "reviewer"},
			{"name": "done", "kind": "terminal_success"},
		],
		"transitions": [
			{
				"id": f"{key}_submit",
				"event": "submit",
				"from_state": "draft",
				"to_state": "review",
				"priority": 0,
				"guards": [],
				"gates": [],
				"effects": [],
			},
			{
				"id": f"{key}_approve",
				"event": "approve",
				"from_state": "review",
				"to_state": "done",
				"priority": 0,
				"guards": [],
				"gates": [],
				"effects": [],
			},
		],
	}
