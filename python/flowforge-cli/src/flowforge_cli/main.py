"""Top-level Typer app for the ``flowforge`` console entry point.

Each command is implemented in its own module under
:mod:`flowforge_cli.commands` and registered here. Subcommand modules
expose a ``register(app)`` callable that mounts the command onto the
root app — keeps imports cheap and makes the wiring obvious.
"""

from __future__ import annotations

import typer

from .commands import (
	add_jtbd,
	ai_assist,
	audit_verify,
	diff,
	migrate_fork,
	new,
	regen_catalog,
	replay,
	simulate,
	upgrade_deps,
	validate,
)

app = typer.Typer(
	name="flowforge",
	help="flowforge framework CLI — scaffold, validate, simulate workflows.",
	no_args_is_help=True,
	add_completion=False,
)

# Audit subgroup (matches §10.1 `flowforge audit verify`).
audit_app = typer.Typer(name="audit", help="Audit-trail tools.", no_args_is_help=True)
app.add_typer(audit_app, name="audit")

# Each module owns one command; this loop keeps wiring obvious.
new.register(app)
add_jtbd.register(app)
regen_catalog.register(app)
validate.register(app)
simulate.register(app)
diff.register(app)
replay.register(app)
upgrade_deps.register(app)
migrate_fork.register(app)
ai_assist.register(app)
audit_verify.register(audit_app)


def main() -> None:
	"""Entry-point shim used by the ``flowforge`` console script."""

	app()


if __name__ == "__main__":  # pragma: no cover
	main()
