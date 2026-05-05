"""``flowforge diff`` — pretty diff of two workflow versions.

Skeleton: a complete implementation is deferred to a follow-up unit; the
command is mounted so the CLI surface matches §10.1.
"""

from __future__ import annotations

from pathlib import Path

import typer


def register(app: typer.Typer) -> None:
	app.command("diff", help="Pretty diff of two workflow definition versions (skeleton).")(diff_cmd)


def diff_cmd(
	a: Path = typer.Argument(..., help="First definition / version id."),
	b: Path = typer.Argument(..., help="Second definition / version id."),
) -> None:
	"""Stub — raises NotImplementedError per the unit's complexity-split rule."""

	raise NotImplementedError(
		f"flowforge diff is not yet implemented (compared {a!s} vs {b!s})."
	)
