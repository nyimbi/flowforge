"""``flowforge status`` - show Flowforge workspace state."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.panel import Panel
from rich.table import Table

from .._ux import console, error, success


def register(app: typer.Typer) -> None:
	app.command(
		"status",
		help="Show current project state: packages, tests, and versions.",
		epilog="[bold]--example[/]: flowforge status --root .",
	)(status_cmd)


def status_cmd(
	root: Annotated[
		Path,
		typer.Option(
			"--root",
			help="Directory to inspect as the Flowforge workspace root (Path, default: current directory).",
		),
	] = Path.cwd(),
	as_json: Annotated[
		bool,
		typer.Option(
			"--json",
			help="Emit machine-readable JSON instead of Rich tables (bool, default: false).",
		),
	] = False,
) -> None:
	"""Show the current Flowforge project state."""

	workspace = _find_workspace_root(root)
	if workspace is None:
		error(
			"Could not find a Flowforge workspace.",
			why=f"{root} is not inside a directory with a pyproject.toml and python/ packages.",
			next_step="Run from the repository root or pass --root /path/to/flowforge.",
		)
		raise typer.Exit(1)

	state = _collect_status(workspace)
	if as_json:
		console.print(json.dumps(state, indent=2, sort_keys=True), markup=False, soft_wrap=True)
		return

	console.print(
		Panel(
			f"[bold]Workspace[/]: {workspace}\n"
			f"[bold]Version[/]: {state['version']}\n"
			f"[bold]Packages[/]: {state['package_count']}\n"
			f"[bold]Tests[/]: {state['test_file_count']} files, {state['test_count']} tests",
			title="Flowforge Status",
			border_style="green",
		)
	)

	summary = Table(title="Project State", show_header=True, header_style="bold")
	summary.add_column("Metric")
	summary.add_column("Value", justify="right")
	for label, value in (
		("Workspace", str(workspace)),
		("flowforge-cli", str(state["version"])),
		("Packages", str(state["package_count"])),
		("Test files", str(state["test_file_count"])),
		("Test functions", str(state["test_count"])),
	):
		summary.add_row(label, value)
	console.print(summary)

	packages = Table(title="Python Packages", show_header=True, header_style="bold")
	packages.add_column("Package")
	packages.add_column("Version")
	for package in state["packages"]:
		packages.add_row(package["name"], package["version"])
	console.print(packages)
	success("status report complete")


def _find_workspace_root(start: Path) -> Path | None:
	current = start.expanduser().resolve()
	candidates = [current, *current.parents]
	for path in candidates:
		if (path / "pyproject.toml").is_file() and (path / "python").is_dir():
			return path
	return None


def _collect_status(workspace: Path) -> dict[str, Any]:
	packages = []
	for pyproject in sorted((workspace / "python").glob("flowforge*/pyproject.toml")):
		meta = _read_project_metadata(pyproject)
		packages.append(
			{
				"name": str(meta.get("name") or pyproject.parent.name),
				"version": str(meta.get("version") or "unknown"),
			}
		)

	test_files = sorted((workspace / "tests").rglob("test_*.py")) if (workspace / "tests").exists() else []
	for tests_dir in sorted((workspace / "python").glob("flowforge*/tests")):
		test_files.extend(sorted(tests_dir.rglob("test_*.py")))
	test_count = 0
	test_pattern = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]+\s*\(")
	for path in test_files:
		try:
			test_count += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if test_pattern.match(line))
		except OSError:
			continue

	cli_project = workspace / "python" / "flowforge-cli" / "pyproject.toml"
	cli_meta = _read_project_metadata(cli_project) if cli_project.exists() else {}
	return {
		"workspace": str(workspace),
		"version": str(cli_meta.get("version") or "unknown"),
		"package_count": len(packages),
		"packages": packages,
		"test_file_count": len(test_files),
		"test_count": test_count,
	}


def _read_project_metadata(pyproject: Path) -> dict[str, Any]:
	try:
		data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
	except (OSError, tomllib.TOMLDecodeError):
		return {}
	project = data.get("project")
	return project if isinstance(project, dict) else {}
