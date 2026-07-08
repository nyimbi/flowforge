"""Top-level Typer app for the ``flowforge`` console entry point.

Each command is implemented in its own module under
:mod:`flowforge_cli.commands` and registered here. Subcommand modules
expose a ``register(app)`` callable that mounts the command onto the
root app — keeps imports cheap and makes the wiring obvious.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._ux import configure_verbosity, error, install_rich_echo, verbose

install_rich_echo(typer)

from .commands import (
	add_jtbd,
	ai_assist,
	audit_2026_health,
	audit_verify,
	bundle_diff,
	diff,
	generate_llmtxt,
	lint_jtbd,
	jtbd_ai_draft,
	jtbd_bundle_fork,
	jtbd_compliance_lint,
	jtbd_desktop,
	tutorial,
	jtbd_fork,
	jtbd_generate,
	jtbd_lint,
	jtbd_lock,
	jtbd_migrate,
	jtbd_quality_score,
	migrate_fork,
	migration_safety,
	new,
	new_workflow,
	polish_copy,
	pre_upgrade_check,
	regen_catalog,
	replay,
	simulate,
	status,
	upgrade_deps,
	validate,
)

app = typer.Typer(
	name="flowforge",
	help="[bold]flowforge[/] framework CLI - scaffold, validate, simulate workflows.",
	epilog="[bold]--example[/]: flowforge status",
	no_args_is_help=True,
	add_completion=False,
	rich_markup_mode="rich",
)

# Audit subgroup (matches §10.1 `flowforge audit verify`).
audit_app = typer.Typer(
	name="audit",
	help="Audit-trail tools.",
	epilog="[bold]--example[/]: flowforge audit verify --file audit.jsonl",
	no_args_is_help=True,
	rich_markup_mode="rich",
)
app.add_typer(audit_app, name="audit")

# JTBD lifecycle subgroup (evolution.md §3 — E-2+).
jtbd_app = typer.Typer(
	name="jtbd",
	help="JTBD lifecycle commands (fork, publish, lock).",
	epilog="[bold]--example[/]: flowforge jtbd lint --bundle workflows/jtbd_bundle.json",
	no_args_is_help=True,
	rich_markup_mode="rich",
)
app.add_typer(jtbd_app, name="jtbd")


@app.callback()
def root_options(
	verbose_flag: Annotated[
		bool,
		typer.Option(
			"--verbose",
			"-v",
			help="Print diagnostic details while commands run (bool, default: false).",
		),
	] = False,
	quiet: Annotated[
		bool,
		typer.Option(
			"--quiet",
			"-q",
			help="Suppress non-error output for scripts (bool, default: false).",
		),
	] = False,
) -> None:
	"""Configure global output controls for every command."""

	if verbose_flag and quiet:
		error(
			"Global verbosity flags conflict.",
			why="--verbose asks for more output while --quiet suppresses non-error output.",
			next_step="Choose either --verbose or --quiet, not both.",
		)
		raise typer.Exit(2)
	configure_verbosity(verbose=verbose_flag, quiet=quiet)
	verbose("verbose output enabled")


# Each module owns one command; this loop keeps wiring obvious.
status.register(app)
new.register(app)
new_workflow.register(app)
add_jtbd.register(app)
jtbd_generate.register(app)
regen_catalog.register(app)
validate.register(app)
simulate.register(app)
diff.register(app)
replay.register(app)
upgrade_deps.register(app)
pre_upgrade_check.register(app)
audit_2026_health.register(app)
migration_safety.register(app)
bundle_diff.register(app)
migrate_fork.register(app)
ai_assist.register(app)
generate_llmtxt.register(app)
polish_copy.register(app)
lint_jtbd.register(app)
audit_verify.register(audit_app)
jtbd_fork.register(jtbd_app)
jtbd_desktop.register(jtbd_app)
jtbd_lint.register(jtbd_app)
jtbd_lock.register(jtbd_app)
jtbd_bundle_fork.register(jtbd_app)
jtbd_migrate.register(jtbd_app)
jtbd_ai_draft.register(jtbd_app)
jtbd_quality_score.register(jtbd_app)
jtbd_compliance_lint.register(jtbd_app)

tutorial.register(app)


_COMMAND_EXAMPLES = {
	"status": "flowforge status --root .",
	"new": "flowforge new claims --jtbd examples/claims.json --out ./apps",
	"new-workflow": "flowforge new-workflow claim-intake --subject-kind claim",
	"add-jtbd": "flowforge add-jtbd extra-jtbd.json --project ./apps/claims",
	"jtbd-generate": "flowforge jtbd-generate --jtbd bundle.json --out generated --force",
	"regen-catalog": "flowforge regen-catalog --root workflows",
	"validate": "flowforge validate --root workflows",
	"simulate": "flowforge simulate --def workflows/claim/definition.json --events submit",
	"diff": "flowforge diff old.json new.json --exit-zero",
	"replay": "flowforge replay --def workflows/claim/definition.json --events-file events.json",
	"upgrade-deps": "flowforge upgrade-deps --root .",
	"pre-upgrade-check": "flowforge pre-upgrade-check signing",
	"audit-2026": "flowforge audit-2026 health --prometheus-url http://localhost:9090",
	"audit-2026 health": "flowforge audit-2026 health --prometheus-url http://localhost:9090",
	"migration-safety": "flowforge migration-safety --migrations-dir backend/migrations/versions",
	"bundle-diff": "flowforge bundle-diff old-bundle.json new-bundle.json",
	"migrate-fork": "flowforge migrate-fork workflows/base/definition.json --to tenant-a",
	"ai-assist": "flowforge ai-assist workflows/jtbd_bundle.json --job claim_intake",
	"generate-llmtxt": "flowforge generate-llmtxt --bundle workflows/jtbd_bundle.json",
	"polish-copy": "flowforge polish-copy --bundle workflows/jtbd_bundle.json --dry-run",
	"lint-jtbd": "flowforge lint-jtbd claim_intake.json --strict",
	"tutorial": "flowforge tutorial --out flowforge-demo --no-pause",
	"audit verify": "flowforge audit verify --file audit-export.jsonl",
	"jtbd fork": "flowforge jtbd fork upstream.json --tenant tenant-a",
	"jtbd desktop": "flowforge jtbd desktop --bundle workflows/jtbd_bundle.json",
	"jtbd lint": "flowforge jtbd lint --bundle workflows/jtbd_bundle.json --strict",
	"jtbd lock": "flowforge jtbd lock --bundle workflows/jtbd_bundle.json --init",
	"jtbd bundle-fork": "flowforge jtbd bundle-fork source.json target_name",
	"jtbd migrate": "flowforge jtbd migrate --bundle jtbd-bundle.json --from old_job",
	"jtbd ai-draft": "flowforge jtbd ai-draft 'A customer opens a claim' --domain claims",
	"jtbd quality-score": "flowforge jtbd quality-score jtbd-bundle.json --threshold 70",
	"jtbd compliance-lint": "flowforge jtbd compliance-lint --bundle jtbd-bundle.json",
}


def _apply_example_epilogs(group: typer.Typer, prefix: str = "") -> None:
	"""Ensure every registered command has a concrete example in its epilog."""

	for command_info in group.registered_commands:
		name = command_info.name
		if not name and command_info.callback is not None:
			name = command_info.callback.__name__.removesuffix("_cmd").replace("_", "-")
		if not name:
			continue
		key = f"{prefix} {name}".strip()
		example = _COMMAND_EXAMPLES.get(key) or _COMMAND_EXAMPLES.get(name)
		if example and not command_info.epilog:
			command_info.epilog = f"[bold]--example[/]: {example}"
	for group_info in group.registered_groups:
		name = group_info.name
		if not name:
			info = getattr(group_info.typer_instance, "info", None)
			name = getattr(info, "name", None)
		if not name:
			continue
		key = f"{prefix} {name}".strip()
		example = _COMMAND_EXAMPLES.get(key)
		if example and not group_info.typer_instance.info.epilog:
			group_info.typer_instance.info.epilog = f"[bold]--example[/]: {example}"
		_apply_example_epilogs(group_info.typer_instance, key)


_apply_example_epilogs(app)


def main() -> None:
	"""Entry-point shim used by the ``flowforge`` console script."""

	app()


if __name__ == "__main__":  # pragma: no cover
	main()
