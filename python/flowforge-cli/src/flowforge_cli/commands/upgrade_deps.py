"""``flowforge upgrade-deps`` — inspect adapter package dependency declarations."""

from __future__ import annotations

import tomllib
from pathlib import Path

import typer


def register(app: typer.Typer) -> None:
	app.command("upgrade-deps", help="Inspect Flowforge adapter dependency pins and optional upgrade plan.")(upgrade_deps_cmd)


def upgrade_deps_cmd(
	root: Path = typer.Option(Path("."), "--root", exists=True, file_okay=False, help="Flowforge checkout root."),
	apply: bool = typer.Option(False, "--apply", help="Reserved for future automated rewrites; currently refuses mutation."),
) -> None:
	"""Report package dependency declarations without mutating the checkout."""

	if apply:
		typer.echo(
			"error: --apply is intentionally unavailable; inspect the plan and edit package pins in reviewable commits",
			err=True,
		)
		raise typer.Exit(2)
	package_roots = sorted((root / "python").glob("flowforge-*/pyproject.toml"))
	if not package_roots:
		typer.echo(f"error: no Flowforge package pyproject.toml files under {root / 'python'}", err=True)
		raise typer.Exit(2)
	typer.echo("Flowforge dependency inspection")
	for pyproject in package_roots:
		data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
		project = data.get("project") or {}
		name = project.get("name") or pyproject.parent.name
		deps = project.get("dependencies") or []
		typer.echo(f"- {name}: {len(deps)} runtime dependencies")
		for dep in deps:
			if isinstance(dep, str) and dep.startswith("flowforge"):
				typer.echo(f"    {dep}")
	typer.echo("No files changed. Use uv lock / package-specific pyproject edits for reviewed upgrades.")
