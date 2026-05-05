"""``flowforge upgrade-deps`` — bump adapter packages.

Skeleton stub.
"""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
	app.command("upgrade-deps", help="Bump adapter packages to latest mutually compatible (skeleton).")(upgrade_deps_cmd)


def upgrade_deps_cmd() -> None:
	raise NotImplementedError("flowforge upgrade-deps is not yet implemented.")
